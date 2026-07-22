from __future__ import annotations

import argparse
import os
import sys

from .capture import (
    CaptureError,
    capture_mercado_livre,
    capture_mercado_livre_browser,
    save_message,
)
from .config import load_env
from .coupons import coupon_for_offer
from .database import OfferRepository
from .formatting import format_offer
from .importers import import_csv
from .models import Offer
from .marketing import PHRASES, category_for, headline_for
from .meli import MeliError, api_get, authorization_url, exchange_callback
from .scheduling import PublicationPolicy
from .publishers import (
    telegram_send,
    whatsapp_outbox,
    whatsapp_share_url,
    whatsapp_web_open,
    whatsapp_web_send,
)
from .wppconnect import WppConnectClient, WppConnectError, group_rows, save_qr_code


def repository() -> OfferRepository:
    repo = OfferRepository(os.getenv("LOOT_DATABASE", "loot_ofertas.db"))
    repo.initialize()
    return repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loot-ofertas")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Cria o banco local")

    sub.add_parser("meli-auth-url", help="Gera a URL segura de autorização do Mercado Livre")
    meli_exchange = sub.add_parser("meli-auth-exchange", help="Troca o retorno OAuth por tokens locais")
    meli_exchange.add_argument(
        "callback", nargs="?", help="URL completa retornada; por padrão lê MELI_CALLBACK_URL do .env"
    )
    sub.add_parser("meli-test", help="Testa a API autenticada do Mercado Livre")

    whatsapp_setup = sub.add_parser("whatsapp-setup", help="Conecta e configura o WPPConnect")
    whatsapp_setup.add_argument("--list-groups", action="store_true")

    add = sub.add_parser("add", help="Adiciona uma oferta com link oficial de afiliado")
    add.add_argument("--title", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--price", required=True, type=float)
    add.add_argument("--store", required=True)
    add.add_argument("--original-price", type=float)
    add.add_argument("--commission", type=float)
    add.add_argument("--coupon")
    add.add_argument("--category")
    add.add_argument("--image-url")

    csv_parser = sub.add_parser("import-csv", help="Importa ofertas de uma planilha CSV")
    csv_parser.add_argument("path")

    capture = sub.add_parser("capture", help="Captura e salva um produto do Mercado Livre")
    capture.add_argument("url")
    capture.add_argument("--no-message", action="store_true", help="Não salva a prévia em arquivo")

    listing = sub.add_parser("list", help="Lista as melhores ofertas prontas")
    listing.add_argument("--limit", type=int, default=10)
    listing.add_argument("--min-score", type=float, default=float(os.getenv("LOOT_MIN_SCORE", "25")))

    status = sub.add_parser("queue-status", help="Mostra limites e próximas ofertas elegíveis")
    status.add_argument("--channel", choices=("telegram", "whatsapp-web", "wppconnect"), default="wppconnect")
    status.add_argument("--limit", type=int, default=5)
    status.add_argument("--min-score", type=float, default=float(os.getenv("LOOT_MIN_SCORE", "25")))

    publish = sub.add_parser("publish", help="Publica ou prepara a melhor oferta")
    publish.add_argument("channel", choices=("telegram", "whatsapp", "whatsapp-web", "wppconnect"))
    publish.add_argument("--limit", type=int, default=1)
    publish.add_argument("--min-score", type=float, default=float(os.getenv("LOOT_MIN_SCORE", "25")))
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--force", action="store_true", help="Ignora limites para um teste manual")
    publish.add_argument("--offer-id", type=int, help="Seleciona uma oferta específica")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    repo = repository()
    if args.command == "init":
        print("Banco criado com sucesso.")
        return 0
    if args.command == "meli-auth-url":
        try:
            print(authorization_url())
            return 0
        except MeliError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "meli-auth-exchange":
        try:
            callback = args.callback or os.getenv("MELI_CALLBACK_URL", "").strip()
            if not callback:
                raise MeliError("Cole a URL retornada em MELI_CALLBACK_URL no arquivo .env.")
            token = exchange_callback(callback)
            print(f"Autorização salva. Token válido por {token.get('expires_in', 21600)} segundos.")
            return 0
        except MeliError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "meli-test":
        try:
            user = api_get("users/me")
            print(f"API conectada: usuário {user.get('nickname') or user.get('id')}.")
            return 0
        except MeliError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "whatsapp-setup":
        try:
            client = _wppconnect_client()
            if args.list_groups:
                rows = group_rows(client.groups())
                if not rows:
                    print("Nenhum grupo encontrado. Confirme se a sessão está conectada.")
                for name, group_id in rows:
                    print(f"{name} | {group_id}")
                return 0
            response = client.start_session()
            qr_path = save_qr_code(response)
            if qr_path:
                print(f"QR Code salvo em: {qr_path}")
                print("Escaneie em WhatsApp > Aparelhos conectados e depois execute com --list-groups.")
            else:
                print("Sessão iniciada. Se já estava autenticada, não é necessário ler outro QR Code.")
            return 0
        except WppConnectError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "add":
        offer = Offer(
            title=args.title, affiliate_url=args.url, price=args.price,
            original_price=args.original_price, commission_percent=args.commission,
            store=args.store, coupon=args.coupon, category=args.category,
            image_url=args.image_url,
        )
        offer_id = repo.add(offer)
        print(f"Oferta {offer_id} salva com score {offer.score}.")
        return 0
    if args.command == "import-csv":
        print(f"{import_csv(args.path, repo)} ofertas importadas.")
        return 0
    if args.command == "capture":
        try:
            captured = capture_mercado_livre(args.url)
        except CaptureError as direct_error:
            print(f"Leitura direta indisponível ({direct_error}). Tentando pelo navegador...")
            try:
                captured = capture_mercado_livre_browser(
                    args.url, session_dir=os.getenv("CAPTURE_SESSION_DIR", ".capture-session")
                )
            except CaptureError as browser_error:
                print(f"Captura recusada: {browser_error}", file=sys.stderr)
                return 2
        offer = captured.offer
        offer.category = category_for(offer)
        offer_id = repo.add(offer)
        offer.id = offer_id
        offer.headline = headline_for(offer, repo.recent_headlines(offer.category, 10))
        message = format_offer(offer)
        print(f"Oferta {offer_id} capturada: {offer.title}")
        print(f"Preço: R$ {offer.price:.2f} | Categoria: {offer.category}")
        if not args.no_message:
            path = save_message(message, offer_id)
            print(f"Mensagem salva em: {path}")
        print("\n" + message)
        return 0
    if args.command == "queue-status":
        policy = PublicationPolicy.from_env()
        decision = repo.publication_decision(args.channel, policy)
        print(f"Canal: {args.channel}")
        print(f"Envio agora: {'sim' if decision.allowed else 'não'} ({decision.reason})")
        print(
            f"Política: {policy.start_hour:02d}:00–{policy.end_hour:02d}:00 | "
            f"intervalo {policy.min_interval_minutes} min | máximo {policy.daily_limit}/dia | "
            f"máximo {policy.category_daily_limit}/categoria"
        )
        offers = repo.eligible_ready(args.channel, policy, args.limit, args.min_score)
        if not offers:
            print("Fila elegível vazia.")
        for position, offer in enumerate(offers, 1):
            print(f"{position}. [{offer.id}] score={offer.score:.2f} | {offer.title} | R$ {offer.price:.2f}")
        return 0
    if args.command == "list":
        offers = repo.ready(args.limit, args.min_score)
        for offer in offers:
            print(f"[{offer.id}] score={offer.score:.2f} | {offer.title} | {offer.affiliate_url}")
        return 0
    policy = PublicationPolicy.from_env()
    sends_immediately = args.channel in {"telegram", "whatsapp-web", "wppconnect"}
    if sends_immediately and not args.dry_run and not args.force:
        decision = repo.publication_decision(args.channel, policy)
        if not decision.allowed:
            suffix = (
                f" Aguarde cerca de {max(1, decision.wait_seconds // 60 + 1)} minuto(s)."
                if decision.wait_seconds else ""
            )
            print(f"Publicação adiada: {decision.reason}.{suffix}")
            return 0
    requested_limit = args.limit if args.dry_run or not sends_immediately else 1
    if args.offer_id is not None:
        selected = repo.get(args.offer_id)
        offers = [selected] if selected and (args.force or selected.status == "ready") else []
    else:
        offers = repo.eligible_ready(args.channel, policy, requested_limit, args.min_score)
    if not offers:
        print("Nenhuma oferta atingiu o score mínimo.")
        return 0
    whatsapp_driver = None
    if args.command == "publish" and args.channel == "whatsapp-web" and not args.dry_run:
        group_name = os.getenv("WHATSAPP_GROUP_NAME", "Loot de Ofertas Gamers")
        session_dir = os.getenv("WHATSAPP_SESSION_DIR", ".whatsapp-session")
        whatsapp_driver = whatsapp_web_open(session_dir)
    wpp_client = None
    wpp_group_id = None
    if args.command == "publish" and args.channel == "wppconnect" and not args.dry_run:
        try:
            wpp_client = _wppconnect_client()
            wpp_group_id = os.getenv("WPP_GROUP_ID") or wpp_client.find_group(
                os.getenv("WHATSAPP_GROUP_NAME", "Loot de Ofertas Gamers")
            )
        except WppConnectError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    for index, offer in enumerate(offers):
        if not offer.coupon and offer.store.casefold() == "magalu":
            coupons_url = os.getenv("MAGALU_COUPONS_URL", "")
            if coupons_url:
                offer.coupon = coupon_for_offer(offer, coupons_url)
        phrase_category = category_for(offer)
        recent = repo.recent_headlines(phrase_category, 10)
        offer.headline = headline_for(offer, recent)
        if args.dry_run:
            print(format_offer(offer), "\n")
            continue
        if args.channel == "telegram":
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                print("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.", file=sys.stderr)
                return 2
            telegram_send(offer, token, chat_id)
            repo.record_headline(offer, phrase_category)
            repo.mark_published(offer.id, args.channel, phrase_category)
            print(f"Oferta {offer.id} publicada no Telegram.")
        elif args.channel == "whatsapp":
            path = whatsapp_outbox(offer)
            print(f"Mensagem salva em {path}")
            print(f"Compartilhamento manual: {whatsapp_share_url(offer)}")
        elif args.channel == "whatsapp-web":
            whatsapp_web_send(whatsapp_driver, group_name, offer)
            repo.record_headline(offer, phrase_category)
            repo.mark_published(offer.id, args.channel, phrase_category)
            print(f"Oferta {offer.id} publicada no grupo {group_name}.")
        else:
            try:
                wpp_client.send_offer(
                    wpp_group_id, offer, os.getenv("WHATSAPP_IMAGE_MODE", "link-preview")
                )
            except WppConnectError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            repo.record_headline(offer, phrase_category)
            repo.mark_published(offer.id, args.channel, phrase_category)
            print(f"Oferta {offer.id} publicada no grupo pelo WPPConnect.")
    keep_open = os.getenv("WHATSAPP_KEEP_OPEN", "false").casefold() in {"1", "true", "yes", "sim"}
    if whatsapp_driver is not None and not keep_open:
        whatsapp_driver.quit()
    return 0


def _wppconnect_client() -> WppConnectClient:
    token = os.getenv("WPP_TOKEN")
    if not token:
        raise WppConnectError("Configure WPP_TOKEN no arquivo .env.")
    return WppConnectClient(
        os.getenv("WPP_BASE_URL", "http://localhost:21465"),
        os.getenv("WPP_SESSION", "loot-ofertas"),
        token,
    )


if __name__ == "__main__":
    raise SystemExit(main())
