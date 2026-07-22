from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

from .capture import (
    CaptureError,
    capture_mercado_livre,
    capture_mercado_livre_api,
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
from .market import MarketQuote, MarketRepository, assess_deal, google_shopping_quotes
from .magalu import capture_magalu, capture_magalu_browser
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
    compare = sub.add_parser("compare", help="Compara uma oferta com o mercado atual")
    compare.add_argument("offer_id", type=int)
    compare.add_argument("--google", action="store_true", help="Atualiza pelo Google Shopping via SerpApi")
    monitor = sub.add_parser("monitor", help="Atualiza comparações sem publicar")
    monitor.add_argument("--limit", type=int, default=10)
    monitor.add_argument("--google", action="store_true", help="Consulta Google Shopping via SerpApi")
    market_add = sub.add_parser("market-add", help="Adiciona preço concorrente ao portfólio")
    market_add.add_argument("offer_id", type=int, help="Oferta usada como produto de referência")
    market_add.add_argument("--store", required=True)
    market_add.add_argument("--price", required=True, type=float)
    market_add.add_argument("--url", required=True)
    market_add.add_argument("--shipping", type=float)
    market_add.add_argument("--title", help="Título na outra loja; usa o título da oferta se omitido")

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
    if args.command == "compare":
        offer = repo.get(args.offer_id)
        if not offer:
            print(f"Oferta {args.offer_id} não encontrada.", file=sys.stderr)
            return 2
        _record_and_compare(repo, offer, use_google=args.google)
        return 0
    if args.command == "monitor":
        offers = repo.ready(args.limit, min_score=-999)
        if not offers:
            print("Nenhuma oferta disponível para monitorar.")
            return 0
        for offer in offers:
            print(f"\n[{offer.id}] {offer.title}")
            offer = _refresh_offer(repo, offer)
            _record_and_compare(repo, offer, use_google=args.google)
        return 0
    if args.command == "market-add":
        offer = repo.get(args.offer_id)
        if not offer:
            print(f"Oferta {args.offer_id} não encontrada.", file=sys.stderr)
            return 2
        market = MarketRepository(repo.path)
        market.record(MarketQuote(
            title=args.title or offer.title, store=args.store, price=args.price,
            shipping_price=args.shipping, source_url=args.url, source="portfolio_manual",
        ))
        _record_and_compare(repo, offer, use_google=False)
        return 0
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
        offer.id = offer_id
        _record_and_compare(repo, offer, use_google=bool(os.getenv("SERPAPI_API_KEY")))
        print(f"Oferta {offer_id} salva com score {offer.score}.")
        return 0
    if args.command == "import-csv":
        print(f"{import_csv(args.path, repo)} ofertas importadas.")
        return 0
    if args.command == "capture":
        host = (urllib.parse.urlsplit(args.url).hostname or "").casefold()
        if "magazineluiza.com.br" in host or "magazinevoce.com.br" in host:
            try:
                captured = capture_magalu(args.url)
                print("Produto consultado na página pública do Magalu.")
            except CaptureError as direct_error:
                print(f"Leitura Magalu indisponível ({direct_error}). Tentando pelo navegador...")
                try:
                    captured = capture_magalu_browser(
                        args.url, session_dir=os.getenv("MAGALU_SESSION_DIR", ".magalu-session")
                    )
                except CaptureError as browser_error:
                    print(f"Captura recusada: {browser_error}", file=sys.stderr)
                    return 2
        else:
            try:
                captured = capture_mercado_livre_api(args.url)
                print("Produto consultado pela API oficial do Mercado Livre.")
            except CaptureError as api_error:
                print(f"API indisponível ({api_error}). Tentando leitura direta...")
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
        _record_and_compare(repo, offer, use_google=bool(os.getenv("SERPAPI_API_KEY")))
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
        assessment = _record_and_compare(repo, offer, use_google=False)
        if (
            not args.force and not args.dry_run
            and assessment.label not in {"imperdivel", "excelente", "promocao"}
        ):
            print(f"Oferta {offer.id} não publicada: avaliação atual é {assessment.label}.")
            continue
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


def _record_and_compare(repo: OfferRepository, offer: Offer, use_google: bool = False):
    market = MarketRepository(repo.path)
    market.record(MarketQuote(
        title=offer.title, store=offer.store, price=offer.price,
        shipping_price=offer.shipping_price, source_url=offer.source_url or offer.affiliate_url,
        rating=offer.seller_rating, reviews=offer.review_count, source="captura_direta",
    ))
    if use_google:
        try:
            for quote in google_shopping_quotes(offer.title):
                market.record(quote)
        except RuntimeError as exc:
            print(f"Comparador Google indisponível: {exc}")
    quotes = market.matching_quotes(offer.title)
    assessment = assess_deal(offer, quotes, repo.prices_for(offer.product_key or ""))
    if offer.id is not None:
        market.save_assessment(offer.id, assessment)
    print(
        f"Avaliação: {assessment.label} | confiança {assessment.confidence} | "
        f"{assessment.competitor_count} concorrente(s)"
    )
    if assessment.market_median is not None:
        print(f"Mediana atual do mercado: R$ {assessment.market_median:.2f}")
    for reason in assessment.reasons:
        print(f"- {reason}")
    return assessment


def _refresh_offer(repo: OfferRepository, offer: Offer) -> Offer:
    url = offer.source_url or offer.affiliate_url
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    try:
        if "mercadolivre.com" in host:
            refreshed = capture_mercado_livre_api(url).offer
        elif "magazineluiza.com.br" in host or "magazinevoce.com.br" in host:
            try:
                refreshed = capture_magalu(url).offer
            except CaptureError:
                refreshed = capture_magalu_browser(
                    url, session_dir=os.getenv("MAGALU_SESSION_DIR", ".magalu-session")
                ).offer
        else:
            print("Fonte sem atualização automática; mantendo a última cotação.")
            return offer
    except CaptureError as exc:
        print(f"Atualização da fonte falhou: {exc}. Mantendo a última cotação.")
        return offer
    refreshed.category = category_for(refreshed)
    previous_id = offer.id
    refreshed.id = repo.add(refreshed)
    if previous_id is not None:
        repo.mark_duplicate(previous_id, refreshed.id)
    print(f"Preço atualizado: R$ {refreshed.price:.2f}")
    return refreshed


if __name__ == "__main__":
    raise SystemExit(main())
