from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductProfile:
    key: str
    label: str
    terms: tuple[str, ...]
    benefit: str
    emoji: str


def _profile(key: str, label: str, terms: str, benefit: str, emoji: str) -> ProductProfile:
    return ProductProfile(key, label, tuple(term.strip() for term in terms.split("|") if term.strip()), benefit, emoji)


# Catálogo de tipos recorrentes em vitrines gamer. Termos específicos vêm primeiro
# para impedir que "mousepad" seja classificado apenas como "mouse", por exemplo.
PRODUCT_PROFILES: tuple[ProductProfile, ...] = (
    _profile("mousepad_rgb", "MOUSEPAD RGB", "mousepad rgb|mouse pad rgb", "MAIS ESPAÇO PRA MIRA E MAIS LUZ PRO SETUP", "🎯✨"),
    _profile("mousepad", "MOUSEPAD", "mousepad|mouse pad|tapete de mouse", "MIRA SOLTA SEM RASPAR A MESA", "🎯🖱️"),
    _profile("mouse_wireless", "MOUSE SEM FIO", "mouse gamer sem fio|mouse wireless|mouse bluetooth", "MIRA LIVRE SEM TRETAR COM O CABO", "🎯📶"),
    _profile("mouse_mmo", "MOUSE MMO", "mouse mmo|mouse com 12 botoes|mouse 12 botoes", "MAIS ATALHOS NA MÃO E MENOS CLICK PERDIDO", "🖱️⚔️"),
    _profile("mouse_gamer", "MOUSE GAMER", "mouse gamer|mouse rgb|mouse para jogos", "CLICK EM DIA E MIRA NO ALVO", "🎯🖱️"),
    _profile("keyboard_60", "TECLADO 60%", "teclado 60%|teclado 60 por cento|teclado compacto gamer", "MAIS ESPAÇO PRA MIRA SEM PERDER O WASD", "⌨️🎯"),
    _profile("keyboard_mechanical", "TECLADO MECÂNICO", "teclado mecanico|switch red|switch blue|switch brown", "TECLA BOA PRA COMBO SAIR LIMPO", "⌨️⚡"),
    _profile("keyboard_membrane", "TECLADO GAMER", "teclado semi mecanico|teclado membrana gamer|teclado gamer", "WASD PRONTO PRA MAIS UMA PARTIDA", "⌨️🎮"),
    _profile("keycap", "KEYCAP", "keycap|teclas pbt|kit de teclas", "VISUAL NOVO SEM TROCAR O TECLADO TODO", "⌨️✨"),
    _profile("keyboard_switch", "SWITCH DE TECLADO", "switch para teclado|switch mecanico avulso|kit switch teclado", "CLICK RENOVADO PRA TECLA NÃO FALHAR", "⌨️🔧"),
    _profile("wrist_rest", "APOIO DE PULSO", "apoio de pulso|descanso de pulso|wrist rest", "MAIS CONFORTO PRA RANKED LONGA", "🖐️🎮"),
    _profile("headset_wireless", "HEADSET SEM FIO", "headset gamer sem fio|headset wireless", "PASSO NO OUVIDO SEM CABO NO CAMINHO", "🎧📶"),
    _profile("headset", "HEADSET GAMER", "headset gamer|fone gamer|headphone gamer", "PASSO CLARO ANTES DO ADVERSÁRIO", "🎧🔊"),
    _profile("earbuds", "FONE TWS", "fone tws gamer|earbuds gamer|fone bluetooth gamer", "ÁUDIO NO JOGO SEM FIO PRA TILTAR", "🎧⚡"),
    _profile("microphone", "MICROFONE", "microfone gamer|microfone condensador|microfone usb", "CALL LIMPA PRA SQUAD OUVIR TUDO", "🎙️🎮"),
    _profile("mic_arm", "BRAÇO DE MICROFONE", "braco articulado microfone|suporte de microfone|pedestal microfone", "MIC NO LUGAR CERTO SEM TOMAR A MESA", "🎙️🔧"),
    _profile("pop_filter", "POP FILTER", "pop filter|filtro anti puff|espuma para microfone", "VOZ LIMPA SEM ESTOURO NA CALL", "🎙️✨"),
    _profile("webcam", "WEBCAM", "webcam gamer|webcam full hd|webcam 1080p|webcam 4k", "IMAGEM BOA PRA LIVE NÃO VIRAR PIXEL", "📷🎮"),
    _profile("capture_card", "PLACA DE CAPTURA", "placa de captura|capture card|captura hdmi", "GAMEPLAY NA LIVE SEM PERDER O PLAY", "🎥🎮"),
    _profile("stream_deck", "CONTROLADOR DE STREAM", "stream deck|controlador de stream|macro pad", "ATALHO NA MÃO PRA LIVE FLUIR", "🎛️🔥"),
    _profile("ring_light", "RING LIGHT", "ring light|anel de luz", "LUZ CERTA PRA CÂMERA NÃO TILTAR", "💡📷"),
    _profile("gaming_speaker", "CAIXA DE SOM GAMER", "caixa de som gamer|soundbar gamer|speaker gamer", "SOM DE RESPEITO FORA DO HEADSET", "🔊🎮"),
    _profile("monitor_4k", "MONITOR 4K", "monitor gamer 4k|monitor 4k", "DETALHE NO ULTRA PRA ENXERGAR TUDO", "🖥️🔥"),
    _profile("monitor_ultrawide", "MONITOR ULTRAWIDE", "monitor ultrawide|monitor ultra wide", "MAIS TELA PRA JOGO E PRA BATALHA", "🖥️↔️"),
    _profile("monitor_240hz", "MONITOR 240HZ", "monitor 240hz|monitor 280hz|monitor 360hz", "FRAME VOANDO E MOVIMENTO LISO", "🖥️⚡"),
    _profile("monitor_144hz", "MONITOR 144HZ", "monitor 144hz|monitor 165hz|monitor 180hz", "MAIS HERTZ E MENOS DESCULPA", "🖥️🔥"),
    _profile("portable_monitor", "MONITOR PORTÁTIL", "monitor portatil|tela portatil", "SEGUNDA TELA SEM PRENDER O SETUP", "🖥️🎒"),
    _profile("monitor_arm", "BRAÇO DE MONITOR", "braco para monitor|suporte articulado monitor", "TELA NA ALTURA E MESA LIVRE", "🖥️🔧"),
    _profile("gaming_chair", "CADEIRA GAMER", "cadeira gamer", "CONFORTO PRA JOGAR SEM DAR DEBUFF NA COLUNA", "🪑🎮"),
    _profile("ergonomic_chair", "CADEIRA ERGONÔMICA", "cadeira ergonomica|cadeira presidente", "POSTURA EM DIA PRA SESSÃO LONGA", "🪑✨"),
    _profile("gaming_desk", "MESA GAMER", "mesa gamer|escrivaninha gamer", "ESPAÇO PRO SETUP SUBIR DE NÍVEL", "🖥️🎮"),
    _profile("desk_mat", "DESK MAT", "desk mat|tapete de mesa", "MESA PROTEGIDA E SETUP ALINHADO", "✨🖥️"),
    _profile("led_strip", "FITA LED RGB", "fita led rgb|fita rgb|led para setup", "RGB LIGADO PRA DAR BUFF NO SETUP", "🌈🎮"),
    _profile("rgb_lamp", "LUMINÁRIA RGB", "luminaria rgb|barra de luz rgb|light bar gamer", "CLIMA DE LOBBY SEM SAIR DO QUARTO", "💡🌈"),
    _profile("headset_stand", "SUPORTE DE HEADSET", "suporte headset|suporte fone gamer", "HEADSET GUARDADO SEM VIRAR LOOT NA MESA", "🎧🧰"),
    _profile("cable_manager", "ORGANIZADOR DE CABOS", "organizador de cabos|kit organizador cabo|canaleta cabo", "MENOS CABO SOLTO E MAIS SETUP LIMPO", "🔌✨"),
    _profile("usb_hub", "HUB USB", "hub usb|hub tipo c|divisor usb", "MAIS PORTA PRA TODO O LOOT", "🔌🎮"),
    _profile("gaming_notebook", "NOTEBOOK GAMER", "notebook gamer|laptop gamer", "FPS NA MOCHILA PRA JOGAR ONDE QUISER", "💻🔥"),
    _profile("gaming_pc", "PC GAMER", "pc gamer|computador gamer|desktop gamer", "SETUP PRONTO PRA RODAR A PARTIDA", "🖥️🔥"),
    _profile("mini_pc", "MINI PC", "mini pc gamer|mini computador|mini pc", "PC COMPACTO SEM JOGAR DE PEQUENO", "🖥️⚡"),
    _profile("gpu_nvidia", "GEFORCE RTX", "geforce rtx|placa de video nvidia|rtx 3050|rtx 3060|rtx 4060|rtx 4070|rtx 4080|rtx 4090|rtx 5060|rtx 5070|rtx 5080|rtx 5090", "MAIS FRAME PRA GRÁFICO NO ULTRA", "🔥🖥️"),
    _profile("gpu_amd", "RADEON RX", "radeon rx|placa de video amd|rx 6600|rx 7600|rx 7700|rx 7800|rx 7900|rx 9060|rx 9070", "FPS ALTO SEM NERFAR O BOLSO", "🔥🖥️"),
    _profile("cpu_ryzen", "PROCESSADOR RYZEN", "ryzen 3|ryzen 5|ryzen 7|ryzen 9|processador amd", "MAIS PODER PRO PC NÃO TILTAR", "🧠⚡"),
    _profile("cpu_intel", "PROCESSADOR INTEL", "core i3|core i5|core i7|core i9|processador intel", "PROCESSAMENTO EM DIA PRA SEGURAR O GAME", "🧠🔥"),
    _profile("motherboard", "PLACA-MÃE", "placa mae|motherboard", "A BASE CERTA PRA TODO O SETUP", "🔧🖥️"),
    _profile("ram_ddr5", "MEMÓRIA DDR5", "memoria ddr5|ram ddr5", "MAIS VELOCIDADE PRA MULTITAREFA NÃO TILTAR", "⚡💾"),
    _profile("ram_ddr4", "MEMÓRIA DDR4", "memoria ddr4|ram ddr4|memoria ram", "MAIS FÔLEGO PRO PC SEGURAR O JOGO", "⚡💾"),
    _profile("ssd_nvme", "SSD NVME", "ssd nvme|ssd m.2|nvme", "LOADING CURTO PRA SOBRAR MAIS GAME", "⚡💾"),
    _profile("ssd_sata", "SSD SATA", "ssd sata|ssd 2.5|ssd 2,5", "PC ACORDADO SEM ESPERAR RESPAWN", "⚡💾"),
    _profile("external_ssd", "SSD EXTERNO", "ssd externo", "JOGO NA MOCHILA COM LOADING RÁPIDO", "💾🎒"),
    _profile("hard_drive", "HD", "hd interno|disco rigido|hd para pc", "ESPAÇO PRO BACKLOG NÃO DAR GAME OVER", "💾🎮"),
    _profile("power_supply", "FONTE", "fonte atx|fonte gamer|fonte 500w|fonte 600w|fonte 650w|fonte 750w|fonte 850w", "ENERGIA CERTA PRA SEGURAR O SETUP", "⚡🔌"),
    _profile("pc_case", "GABINETE GAMER", "gabinete gamer|gabinete aquario|gabinete pc", "CASA NOVA PRO SETUP RESPIRAR", "🖥️✨"),
    _profile("cpu_cooler", "COOLER DE PROCESSADOR", "cooler processador|cpu cooler|air cooler", "CPU FRIA PRA PARTIDA CONTINUAR", "❄️🧠"),
    _profile("water_cooler", "WATER COOLER", "water cooler|refrigeracao liquida", "TEMPERATURA NO LOW E PERFORMANCE NO HIGH", "❄️🔥"),
    _profile("case_fan", "FAN RGB", "fan rgb|ventoinha rgb|cooler gabinete|kit fan", "AR NO GABINETE E RGB NO SETUP", "🌬️🌈"),
    _profile("thermal_paste", "PASTA TÉRMICA", "pasta termica", "CALOR LONGE PRA CPU NÃO PEDIR PAUSA", "❄️🔧"),
    _profile("wifi_adapter", "ADAPTADOR WI-FI", "adaptador wifi|placa wifi|dongle wifi", "CONEXÃO SEM FIO PRA NÃO CAIR DA PARTIDA", "📶🎮"),
    _profile("ethernet_cable", "CABO DE REDE", "cabo de rede|cabo ethernet|cabo cat6|cabo cat7", "PING NO LOW PRA DESCULPA NÃO SER A INTERNET", "🌐⚡"),
    _profile("router_gamer", "ROTEADOR GAMER", "roteador gamer|roteador wifi 6|roteador wifi 7", "SINAL FORTE PRA PARTIDA NÃO DESCONECTAR", "📶🔥"),
    _profile("power_strip", "FILTRO DE LINHA", "filtro de linha|regua de tomada|protetor eletrico", "SETUP LIGADO COM MAIS PROTEÇÃO", "🔌🛡️"),
    _profile("ups", "NOBREAK", "nobreak|no break", "ENERGIA EXTRA PRA NÃO CAIR NO MEIO DA RANKED", "🔋🎮"),
    _profile("ps5_console", "PLAYSTATION 5", "playstation 5|ps5 slim|ps5 pro|console ps5", "NOVA GERAÇÃO PRONTA PRA SALA", "🎮🔥"),
    _profile("xbox_series", "XBOX SERIES", "xbox series x|xbox series s|console xbox series", "GAME PASS E CONTROLE NA MÃO", "🎮💚"),
    _profile("nintendo_switch", "NINTENDO SWITCH", "nintendo switch|switch oled|switch lite", "DIVERSÃO NO DOCK E FORA DE CASA", "🎮🍄"),
    _profile("steam_deck", "STEAM DECK", "steam deck", "BIBLIOTECA DO PC DIRETO NA MÃO", "🎮💻"),
    _profile("handheld_pc", "PORTÁTIL GAMER", "rog ally|legion go|portatil gamer|console portatil windows", "PC GAMER NA MÃO PRA JOGAR EM QUALQUER LUGAR", "🎮⚡"),
    _profile("retro_console", "CONSOLE RETRÔ", "console retro|videogame retro|emulador portatil", "NOSTALGIA COM CONTINUE INFINITO", "🕹️✨"),
    _profile("ps5_controller", "DUALSENSE", "dualsense|controle ps5", "PRÓXIMO CHECKPOINT NA PONTA DOS DEDOS", "🎮🔥"),
    _profile("xbox_controller", "CONTROLE XBOX", "controle xbox|controle sem fio xbox|controle xbox series|xbox wireless controller", "COMBO NA MÃO SEM BRIGAR COM O CONTROLE", "🎮💚"),
    _profile("switch_controller", "CONTROLE SWITCH", "pro controller switch|controle nintendo switch", "COOP PRONTO PRA ENTRAR NO LOBBY", "🎮🍄"),
    _profile("generic_controller", "CONTROLE GAMER", "controle bluetooth|controle para pc|gamepad|joystick|controle gamer", "COMBO LIMPO PRA JOGAR SEM DRIFT", "🎮⚡"),
    _profile("joycon", "JOY-CON", "joy con|joy-con", "PLAYER EXTRA PRONTO PRO COOP", "🎮🍄"),
    _profile("controller_charger", "CARREGADOR DE CONTROLE", "carregador controle|base carregadora controle|dock controle", "BATERIA CHEIA PRA NÃO PAUSAR O GAME", "🔋🎮"),
    _profile("controller_grip", "GRIP DE CONTROLE", "grip controle|capa controle|skin controle", "PEGADA FIRME PRA COMBO NÃO ESCAPAR", "🎮🖐️"),
    _profile("thumb_grip", "GRIP DE ANALÓGICO", "grip analogico|capa analogico|thumb grip", "ANALÓGICO NA MIRA SEM ESCORREGAR", "🎯🎮"),
    _profile("racing_wheel", "VOLANTE GAMER", "volante gamer|volante para pc|volante ps5|volante xbox", "POLE POSITION DIRETO NO SETUP", "🏎️🎮"),
    _profile("racing_pedals", "PEDAL GAMER", "pedal simulador|pedaleira gamer|pedal volante", "ACELERAÇÃO NA MEDIDA PRA BUSCAR O PÓDIO", "🏁🎮"),
    _profile("racing_shifter", "CÂMBIO GAMER", "cambio simulador|alavanca cambio gamer|shifter gamer", "TROCA DE MARCHA PRA SIMULAÇÃO FICAR SÉRIA", "🏎️⚙️"),
    _profile("cockpit", "COCKPIT GAMER", "cockpit gamer|suporte volante|cockpit simulador", "GRID DE LARGADA MONTADO EM CASA", "🏁🪑"),
    _profile("flight_stick", "JOYSTICK DE VOO", "joystick de voo|flight stick|hotas", "DECOLAGEM LIBERADA DIRETO DO SETUP", "✈️🎮"),
    _profile("vr_headset", "ÓCULOS VR", "oculos vr|headset vr|meta quest|realidade virtual", "IMERSÃO PRA ENTRAR DE VEZ NO JOGO", "🥽🎮"),
    _profile("gaming_phone", "CELULAR GAMER", "celular gamer|smartphone gamer|rog phone|redmagic", "FPS NO BOLSO PRA RANQUEAR EM QUALQUER LUGAR", "📱🔥"),
    _profile("phone_controller", "CONTROLE PARA CELULAR", "controle celular|gamepad celular|controle mobile", "MOBILE COM PEGADA DE CONSOLE", "📱🎮"),
    _profile("phone_cooler", "COOLER PARA CELULAR", "cooler celular|resfriador celular|ventoinha celular", "CELULAR FRIO PRA FPS NÃO DERRETER", "❄️📱"),
    _profile("phone_trigger", "GATILHO PARA CELULAR", "gatilho celular|trigger mobile", "CLICK MAIS RÁPIDO PRA BATALHA MOBILE", "📱🎯"),
    _profile("phone_holder", "SUPORTE PARA CELULAR", "suporte celular gamer|suporte celular mesa", "TELA NO LUGAR CERTO PRA JOGAR E ASSISTIR", "📱✨"),
    _profile("gaming_tablet", "TABLET GAMER", "tablet gamer|tablet para jogos", "TELA GRANDE PRA GAME MOBILE FICAR NO ULTRA", "📱🔥"),
    _profile("hdmi_cable", "CABO HDMI", "cabo hdmi 2.1|cabo hdmi|hdmi gamer", "IMAGEM NA TELA SEM PERDER FRAME", "🔌🖥️"),
    _profile("displayport_cable", "CABO DISPLAYPORT", "cabo displayport|display port", "HERTZ LIBERADO PRA TELA VOAR", "🔌⚡"),
    _profile("hdmi_switch", "SWITCH HDMI", "switch hdmi|seletor hdmi|hub hdmi", "MAIS CONSOLE NA TV SEM TROCAR CABO", "🔌🎮"),
    _profile("console_stand", "SUPORTE DE CONSOLE", "suporte ps5|suporte xbox|base vertical console", "CONSOLE FIRME E SETUP ORGANIZADO", "🎮🧰"),
    _profile("console_headset", "HEADSET DE CONSOLE", "headset ps5|headset xbox|headset switch", "CHAT DO SQUAD LIMPO DIRETO DO SOFÁ", "🎧🎮"),
    _profile("game_storage", "ARMAZENAMENTO DE CONSOLE", "ssd ps5|cartao xbox expansion|hd xbox|hd ps5", "MAIS JOGO INSTALADO SEM ESCOLHER FAVORITO", "💾🎮"),
    _profile("memory_card", "CARTÃO DE MEMÓRIA", "micro sd switch|cartao memoria gamer|cartao micro sd", "MAIS ESPAÇO PRO PORTÁTIL NÃO DAR GAME OVER", "💾🎮"),
    _profile("game_case", "ESTOJO DE CONSOLE", "case nintendo switch|estojo console|case steam deck|bolsa console", "CONSOLE PROTEGIDO PRA VIAJAR", "🎒🎮"),
    _profile("game_disc", "JOGO EM MÍDIA FÍSICA", "jogo ps5|jogo ps4|jogo xbox|jogo nintendo switch|midia fisica", "JOGO NOVO PRA AUMENTAR O BACKLOG", "💿🎮"),
    _profile("gift_card", "GIFT CARD", "gift card playstation|gift card xbox|gift card nintendo|gift card steam|cartao presente gamer", "CRÉDITO NA CONTA PRA ESCOLHER O PRÓXIMO GAME", "🎁🎮"),
    _profile("gaming_backpack", "MOCHILA GAMER", "mochila gamer|mochila notebook gamer", "LOOT PROTEGIDO PRA SAIR DO SETUP", "🎒💻"),
    _profile("cleaning_kit", "KIT DE LIMPEZA", "kit limpeza pc|kit limpeza teclado|limpa tela|soprador pc", "SETUP LIMPO PRA POEIRA NÃO VIRAR BOSS", "🧹🎮"),
)


assert len(PRODUCT_PROFILES) == 100, "O catálogo gamer deve manter exatamente 100 tipos"
