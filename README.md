# PulseDeck

Controle de teclado RGB e refrigeração para notebooks **Acer Predator** no Linux.
GTK4 + libadwaita.

> Projeto independente, sem relação com a Acer. "Predator" e "PredatorSense"
> são marcas da Acer e **não** serão usadas no nome publicado.

## Estado atual

Tudo abaixo funciona e foi testado neste hardware (Predator PH315-54):

- Cor individual das **4 zonas** + brilho
- Os 6 efeitos do firmware: estático, respiração, neon, onda, shifting, zoom
- 7 temas prontos
- **4 efeitos por software** que o PredatorSense do Windows não tem:
  arco-íris, carga da CPU, termômetro e respiração suave
- **Modo turbo** ligar/desligar, pela interface e pelo CLI
- **RPM das duas ventoinhas** e temperatura da CPU, ao vivo

Medido ao ligar o turbo: CPU **3061 → 5555 rpm**, GPU **3488 → 5769 rpm**.

As duas últimas exigem o patch em [`kernel/`](kernel/) — o módulo `facer`
original não expõe o turbo nem liga a leitura de ventoinha neste modelo.

- **Daemon de sistema** dono do hardware, com D-Bus, restauração no boot e no
  resume, e os efeitos continuando com a janela fechada
- **Atalhos globais**: `Super+T` turbo, `Super+K` apagar — com notificação
  mostrando o RPM real
- **Ícone no tray** com turbo, RPM ao vivo, temas e efeitos
- **Pintura tecla a tecla**, resolvida para as 4 zonas

Ainda não:

- Empacotamento (deb/PPA, snap)
- Perfil automático por aplicativo

Sobre o OSD: o mockup previa um overlay flutuante, mas o Mutter **não
implementa o `wlr-layer-shell`**, então um app comum não consegue desenhar
sobre a tela no GNOME. A saída possível é a notificação do sistema (é o que
está implementado); o overlay bonito exigiria uma extensão do GNOME Shell,
que é um projeto à parte.

## Instalar

```bash
sudo kernel/instalar.sh          # patch do módulo: turbo + leitura de ventoinha
sudo modprobe -r facer && sudo modprobe facer
sudo ./instalar-daemon.sh        # pulsedeckd no systemd + política D-Bus
./instalar-atalhos.sh            # Super+T e Super+K (sem sudo)
./instalar-tray.sh               # ícone de bandeja (sem sudo)
```

Cada um tem o par `desinstalar-*`/`reverter.sh`. O `instalar-daemon.sh`
desativa o `acer-rgb.service` antigo, que fazia o mesmo trabalho de boot/resume.

## Rodar

```bash
python3 run.py
```

Sem o daemon instalado, a janela fala direto com o hardware (modo
desenvolvimento) — o cabeçalho mostra em qual modo está.

Dependências: `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `python3-gi-cairo`
e o módulo de kernel `facer` carregado.

Para turbo e leitura de ventoinha, aplique o patch do módulo:

```bash
sudo kernel/instalar.sh
sudo modprobe -r facer && sudo modprobe facer
```

Reverter: `sudo kernel/reverter.sh`.

## CLI (para atalhos de teclado)

```bash
python3 run.py --apply           # reaplica o perfil salvo
python3 run.py --off             # apaga o teclado
python3 run.py --theme Matrix    # aplica um tema
python3 run.py --turbo toggle    # alterna o turbo
python3 run.py --turbo on        # liga
```

Para ligar num atalho global do GNOME: Configurações → Teclado → Atalhos
personalizados, com o comando acima.

## Estrutura

| Arquivo | O quê |
|---|---|
| `pulsedeck/hardware.py` | única camada que toca nos `/dev` — vira o `pulsedeckd` depois |
| `pulsedeck/effects.py` | motor de efeitos por software (30 fps, em thread) |
| `pulsedeck/keyboardview.py` | preview do teclado em cairo |
| `pulsedeck/window.py` | janela (sidebar + páginas) |
| `pulsedeck/app.py` | Adw.Application e CLI |
| `pulsedeck/daemon.py` | `pulsedeckd` — serviço de sistema, dono do hardware |
| `pulsedeck/client.py` | backend D-Bus + fallback direto |
| `pulsedeck/tray.py` | ícone de bandeja (StatusNotifierItem + dbusmenu) |
| `pulsedeck/perkey.py` | resolve o mapa tecla-a-tecla para as 4 zonas |
| `kernel/` | patch do módulo `facer` + instalar/reverter |

### Arquitetura

```
GUI ─┐
CLI ─┼─ D-Bus (sistema) ─>  pulsedeckd  ─>  facer 1.1 (DKMS)
Tray ┘                           │
                        /dev/acer-gkbbl-*
                        /sys/.../acer-wmi/turbo
                        hwmon acer (RPM)
```

O tray é um processo próprio da sessão, não parte da janela — um tray que
morre ao fechar a janela não é um tray. Ele implementa
`org.kde.StatusNotifierItem` e `com.canonical.dbusmenu` direto no barramento
de sessão, porque o `AppIndicator3` é GTK-3 e o GObject Introspection não
permite carregar Gtk 3.0 e Gtk 4.0 no mesmo processo.

O daemon é o dono exclusivo dos devices. Isso resolve a disputa entre
processos (a GUI chegou a travar a troca do módulo por *device in use*),
mantém os efeitos rodando com a janela fechada, e é o que permite empacotar
como Flatpak ou snap depois — nada confinado precisa tocar em `/dev`.

O protocolo do hardware está documentado no topo de `hardware.py` — não existe
documentação oficial dele em lugar nenhum.

## Pesquisa

O levantamento completo — limitações do hardware, protocolo descoberto por
engenharia reversa, arquitetura, roadmap e o porquê da Snap Store ser hostil a
esse tipo de app — está em [`docs/PESQUISA-E-PLANO.md`](docs/PESQUISA-E-PLANO.md).

Os quatro mockups de layout estão em [`docs/mockups/`](docs/mockups/) (PNG mais
o HTML que os gerou), e a prova de conceito que originou os efeitos por
software em [`docs/poc/`](docs/poc/).

## Sobre o nome

`PulseDeck` é provisório. "Predator" e "PredatorSense" são marcas da Acer e
não podem ser usadas no nome publicado. Renomear o repositório depois é
barato — o GitHub mantém o redirecionamento.

## Licença

A definir antes da primeira publicação. O módulo de kernel derivado do `facer`
é GPL-2.0 por herança; o resto do projeto pode ser outra coisa.
