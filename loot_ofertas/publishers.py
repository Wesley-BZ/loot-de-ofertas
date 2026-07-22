from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from time import sleep

from .formatting import format_offer
from .models import Offer


def telegram_send(offer: Offer, token: str, chat_id: str) -> dict:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": format_offer(offer),
            "disable_web_page_preview": False,
        }
    ).encode()
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram recusou a mensagem"))
    return result


def whatsapp_outbox(offer: Offer, outbox: str | Path = "outbox/whatsapp") -> Path:
    destination = Path(outbox)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"oferta-{offer.id or 'nova'}.txt"
    path.write_text(format_offer(offer), encoding="utf-8")
    return path


def whatsapp_share_url(offer: Offer) -> str:
    return "https://wa.me/?" + urllib.parse.urlencode({"text": format_offer(offer)})


def whatsapp_web_open(session_dir: str | Path):
    """Abre o WhatsApp Web em um perfil persistente do Chrome."""
    try:
        from selenium import webdriver
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError("Instale o Selenium com: python -m pip install -e .") from exc

    profile = Path(session_dir).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    driver.get("https://web.whatsapp.com/")
    WebDriverWait(driver, 180).until(
        lambda browser: browser.find_elements("xpath", "//*[@id='side']")
    )
    return driver


def whatsapp_web_send(driver, group_name: str, offer: Offer) -> None:
    """Seleciona um grupo já existente e publica uma oferta."""
    import pyperclip

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    if not offer.image_url:
        offer.image_url = _resolve_product_image(driver, offer.affiliate_url)
    wait = WebDriverWait(driver, 45)
    search = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[@id='side']//*[@role='textbox'][@data-tab='3']",
            )
        )
    )
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(group_name)
    target = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//span[contains(@title, {_xpath_literal(group_name)})]")
        )
    )
    target.click()
    image_mode = os.getenv("WHATSAPP_IMAGE_MODE", "link-preview").casefold()
    if offer.image_url and image_mode == "upload":
        _whatsapp_web_send_image(driver, offer, wait)
        sleep(2)
        return
    box = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//footer//*[@contenteditable='true'][@role='textbox']")
        )
    )
    message = format_offer(offer)
    if offer.image_url and image_mode == "link-preview":
        message = f"{_public_image_url(offer.image_url)}\n\n{message}"
    box.click()
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(Keys.BACKSPACE)
    pyperclip.copy(message)
    box.send_keys(Keys.CONTROL, "v")
    sleep(4)
    box.send_keys(Keys.ENTER)
    sleep(2)


def _public_image_url(image_url: str) -> str:
    return image_url.replace(
        "https://m.magazineluiza.com.br/a-static/",
        "https://a-static.mlcdn.com.br/",
    )


def _whatsapp_web_send_image(driver, offer: Offer, wait) -> None:
    import pyautogui
    import pygetwindow
    import pyperclip
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC

    media_dir = Path("outbox/whatsapp-media")
    media_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urllib.parse.urlparse(offer.image_url).path).suffix or ".jpg"
    image_path = (media_dir / f"oferta-{offer.id or 'nova'}{suffix}").resolve()
    download_url = offer.image_url.replace(
        "https://m.magazineluiza.com.br/a-static/",
        "https://a-static.mlcdn.com.br/",
    )
    request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        data = response.read(10_000_001)
    if not content_type.startswith("image/") or len(data) > 10_000_000:
        raise RuntimeError("A imagem do produto é inválida ou excede 10 MB")
    image_path.write_bytes(data)

    compose = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "footer [contenteditable='true'][role='textbox']")
        )
    )
    compose.click()
    compose.send_keys(Keys.CONTROL, "a")
    compose.send_keys(Keys.BACKSPACE)

    attach = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='Anexar']"))
    )
    driver.execute_script("arguments[0].click()", attach)
    windows = pygetwindow.getWindowsWithTitle("WhatsApp")
    if windows:
        windows[0].restore()
        try:
            windows[0].activate()
        except pygetwindow.PyGetWindowException:
            pass
    wait.until(
        lambda browser: browser.execute_script(
            "return Boolean(document.querySelector('button[aria-label=\"Fotos e vídeos\"]'))"
        )
    )
    driver.execute_script(
        "document.querySelector('button[aria-label=\"Fotos e vídeos\"]').click()"
    )
    sleep(1)
    pyautogui.hotkey("alt", "n")
    pyautogui.write(str(image_path), interval=0.001)
    pyautogui.press("enter")
    from selenium.webdriver.support.ui import WebDriverWait

    media_wait = WebDriverWait(driver, 120)
    debug_dir = Path("outbox/whatsapp-debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str((debug_dir / "1-previa-imagem.png").resolve()))
    caption = media_wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[@placeholder='Digite uma mensagem' or "
                "contains(@aria-label, 'Digite uma mensagem')]",
            )
        )
    )
    caption.click()
    caption.send_keys(Keys.CONTROL, "a")
    caption.send_keys(Keys.BACKSPACE)
    pyperclip.copy(format_offer(offer))
    caption.send_keys(Keys.CONTROL, "v")
    driver.save_screenshot(str((debug_dir / "2-legenda-preenchida.png").resolve()))
    active_windows = pygetwindow.getWindowsWithTitle("WhatsApp")
    if not active_windows:
        raise RuntimeError("Janela do WhatsApp não encontrada para clicar em Enviar")
    active_window = active_windows[0]
    active_window.maximize()
    try:
        active_window.activate()
    except pygetwindow.PyGetWindowException:
        pass
    sleep(1)
    pyautogui.click(
        active_window.left + active_window.width - 48,
        active_window.top + active_window.height - 37,
    )
    media_wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "footer [contenteditable='true'][role='textbox']")
        )
    )
    sleep(3)
    driver.save_screenshot(str((debug_dir / "3-oferta-enviada.png").resolve()))


def _resolve_product_image(driver, affiliate_url: str) -> str | None:
    product_url = affiliate_url
    if "onelink.me" in affiliate_url:
        try:
            html = urllib.request.urlopen(
                urllib.request.Request(affiliate_url, headers={"User-Agent": "Mozilla/5.0"}),
                timeout=20,
            ).read().decode("utf-8", errors="replace")
            match = re.search(r"var store_link = '([^']+)'", html)
            if match:
                product_url = match.group(1)
        except (OSError, TimeoutError):
            return None

    original = driver.current_window_handle
    try:
        driver.switch_to.new_window("tab")
        driver.get(product_url)
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        meta = WebDriverWait(driver, 25).until(
            lambda browser: next(
                iter(browser.find_elements(By.CSS_SELECTOR, "meta[property='og:image']")),
                False,
            )
        )
        return meta.get_attribute("content") or None
    except Exception:
        return None
    finally:
        if driver.current_window_handle != original:
            driver.close()
        driver.switch_to.window(original)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"
