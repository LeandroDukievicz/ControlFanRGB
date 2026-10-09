# PulseDeck — pesquisa de cenário e plano

**Máquina alvo:** Acer Predator PH315-54 (Helios 300, 2021) · BIOS V1.15 · Ubuntu 26.04 · kernel 7.0.0-38
**Base atual:** módulo DKMS `facer/1.0` + CLI `/usr/local/bin/acer-rgb` (funcionando)
**Data da pesquisa:** 09/10/2026 — tudo abaixo foi **testado nesta máquina**, não é suposição.

---

## 1. O que eu confirmei na prática

| # | Achado | Como verifiquei |
|---|--------|-----------------|
| 1 | **O teclado tem 4 zonas, não per-key.** A interface WMI só aceita um *bitmask de zona*, não existe endereço de tecla. | `facer_rgb.py`: `payload[0] = 1 << (zona-1)`; o driver (`facer.c`) não tem nenhum método de tecla individual |
| 2 | **Ler o RPM das ventoinhas funciona** — CPU **3061 rpm**, GPU **3488 rpm** | recarreguei com `modprobe facer predator_v4=1` → apareceu `hwmon` chamado `acer` com `fan1_input`/`fan2_input` |
| 3 | Mas a quirk do PH315-54 **não liga** esse recurso. `predator_v4=1` por parâmetro *troca* a quirk inteira e aí **perde o turbo**. | `facer.c:497` → `FAN_SPEED_READ` só com `quirks->predator_v4`; `facer.c:1298` → o param sobrescreve `quirks` |
| 4 | **O turbo não tem API de userspace.** Só a tecla física do chassi dispara `acer_toggle_turbo()`. | `facer.c:3339` — o toggle só existe dentro do handler `WMID_GAMING_TURBO_KEY_EVENT` |
| 5 | **Escrever cor é baratíssimo: ~0,07 ms.** Dá pra animar por software a ~3700 fps teóricos. | benchmark: 120 frames (5 syscalls cada) em 0,032 s |
| 6 | **Pegadinha séria:** o `/dev/acer-gkbbl-static-0` exige **exatamente 4 bytes por syscall**. Escrita bufferizada do Python junta 4 writes em um de 16 bytes → o driver rejeita e o processo entra em *loop infinito a 100% de CPU*. | aconteceu comigo: processo travado 2,5 min em estado R até eu matar. Solução: `os.write()` em fd cru |
| 7 | `platform_profile` aparece com `predator_v4=1`, mas só com `low-power / quiet / balanced` — **sem `performance`**. Ou seja, turbo não dá pra fazer por ali. | `cat /sys/firmware/acpi/platform_profile_choices` |
| 8 | O CLI atual faz **8 escritas** para pintar 4 zonas (1 write + 1 commit por zona). Dá pra fazer com **5** (4 zonas + 1 commit), ou 2 usando bitmask. | `acer-rgb` linha do loop `for z in 1 2 3 4` |

### Protocolo real do hardware (documentado aqui porque não está em lugar nenhum)

```
/dev/acer-gkbbl-static-0   → 4 bytes:  [bitmask_zona, R, G, B]
                             bitmask: 0b0001=zona1 … 0b1000=zona4 (aceita combinar!)
/dev/acer-gkbbl-0          → 16 bytes: [modo, velocidade, brilho, 8_se_onda, direção,
                                        R, G, B, 0, 1(commit), 0…]
modos: 0 estático · 1 respiração · 2 neon · 3 onda · 4 shifting · 5 zoom
```

---

## 2. As três verdades inconvenientes (e o que fazer com cada uma)

### 2.1 Per-key é fisicamente impossível nesse notebook
O Windows **também não** faz per-key no PH315-54 — o PredatorSense oferece 4 zonas. Per-key só existe
em Helios 16/18 e Triton, que usam outro controlador.

**O que dá pra entregar no lugar (e fica melhor que o Windows):** uma UI de *pintar tecla a tecla* onde
você clica nas teclas, e o app **resolve** a cor de cada zona (média ponderada das teclas que você pintou
naquela faixa). O modelo de dados já nasce per-key, então quando você trocar de notebook o app aproveita
o hardware melhor sem reescrever nada. É o mockup **D**.

### 2.2 Turbo precisa de patch no módulo
Hoje só a tecla física liga. Para ter atalho de teclado + botão na tela, tem que expor no kernel.
Três caminhos:

| Caminho | Esforço | Risco |
|---|---|---|
| **A. Fork do `facer`** com `/sys/devices/platform/acer-wmi/turbo` + quirk corrigida do PH315-54 (`turbo=1, cpu_fans=1, gpu_fans=1, predator_v4=1`) | ~150 linhas de C | baixo — o código do toggle já existe, é só expor |
| B. Migrar pro **Linuwu-Sense**, que já tem `turbo`, `fan_speed` (0–100, controle manual!) e `per_zone_mode` em sysfs | médio | o PH315-54 **não está** na tabela DMI dele (só o -53), e ele instala por `make`, não DKMS |
| C. `acpi_call` chamando os métodos WMI direto do userspace | baixo | gambiarra, instável, e ainda precisa de módulo extra |

**Recomendo A.** É o menor delta sobre o que já funciona aqui, mantém DKMS, e dá pra mandar PR de volta
pro projeto original. Bônus do A: com a quirk corrigida você ganha leitura de RPM **e** turbo ao mesmo tempo.

### 2.3 A Snap Store é o pior lugar pra esse app (e tem jeito)
- Um snap **não pode instalar módulo de kernel**. O DKMS tem que vir por fora (deb/PPA/script).
- Em *strict confinement*, snap **não escreve** em `/dev/acer-gkbbl-*`. Não existe interface padrão pra isso.
- A interface `custom-device` existe, mas é pensada pra Ubuntu Core/gadget snap e **exige aprovação manual da Store**.
- *Classic confinement* resolve, mas **também exige revisão manual** no fórum do Snapcraft.

**Plano de distribuição que eu faria:**
1. **PPA (deb)** como canal principal → instala o DKMS + daemon + GUI de uma vez. É o que realmente funciona.
2. **Snap em classic confinement** depois, pedindo revisão, com o deb do DKMS como pré-requisito documentado.
3. **Flatpak** só se o daemon expuser D-Bus (aí o Flatpak fala com o serviço do sistema e funciona bem).
4. AUR/COPR saem de graça depois.

> ⚠️ **Nome:** "Predator" e "PredatorSense" são marcas da Acer. Não dá pra publicar com esse nome.
> `PulseDeck` é um placeholder meu — outras ideias: `Lumen`, `Chromafan`, `Turbina`, `NeonDeck`.

---

## 3. Arquitetura proposta

```
┌─────────────────────────────────────────────────────────┐
│  GUI (GTK4 + libadwaita)  ← já instalado nessa máquina  │
│  ou Electron, se quiser reaproveitar o stack do          │
│  DerivaSocial/nova-aba-cyberpunk                         │
└───────────────────────────┬─────────────────────────────┘
                            │ D-Bus (sessão → sistema)
┌───────────────────────────▼─────────────────────────────┐
│  pulsedeckd  (daemon de sistema, Python ou Rust)        │
│  • dono exclusivo de /dev/acer-gkbbl-*                   │
│  • motor de animação em software (60 fps, barato)        │
│  • lê hwmon acer → RPM, coretemp → °C                    │
│  • aplica perfil no boot / resume  (mata o systemd atual)│
│  • polkit pra ação privilegiada (turbo)                  │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  facer-plus (DKMS, fork do facer)                        │
│  + sysfs turbo  + quirk PH315-54 com fan read            │
└──────────────────────────────────────────────────────────┘
```

**Por que daemon?** Três motivos concretos: (1) o atalho global e o turbo precisam de privilégio, e você não
quer `pkexec` piscando toda hora; (2) a animação por software precisa rodar mesmo com a janela fechada;
(3) é o que torna Flatpak/Snap viáveis depois — a GUI vira só um cliente.

---

## 4. Funcionalidades

### Base (o que o Windows faz — paridade)
- [ ] 6 efeitos de firmware: estático, respiração, neon, onda, shifting, zoom
- [ ] Cor por zona (4 zonas) com color picker + hex
- [ ] Brilho 0–100, velocidade 0–9, direção
- [ ] Temas prontos: Vapor, Matrix, Inferno, Glacial, Âmbar, Brasil
- [ ] Perfis salvos + aplicar no boot e no resume (já existe, migrar pro daemon)
- [ ] Turbo ligar/desligar + RPM das duas ventoinhas ao vivo

### O que o Windows **não** faz (aqui é onde o projeto ganha identidade)
- [ ] **Efeitos por software** (o benchmark mostrou que cabe folgado):
  - arco-íris real com paleta customizável
  - **zonas reagindo à carga da CPU** (verde → amarelo → vermelho)
  - **termômetro**: cor acompanha a temperatura, vira alerta acima de 85 °C
  - visualizador de áudio (PipeWire)
  - "respiração" seguindo o ritmo de digitação
- [ ] **Pintar tecla a tecla** com resolução automática pra zona (mockup D)
- [ ] Atalhos globais: `Super+T` turbo, `Super+K` apagar teclado, `F1–F5` perfis
- [ ] **OSD** ao ligar o turbo, mostrando RPM real (mockup C)
- [ ] Perfil automático por aplicativo ("abriu Steam → tema Inferno + turbo")
- [ ] Apagar o teclado junto com o bloqueio de tela / na bateria
- [ ] Ícone no tray com RPM

### Fora de escopo (por honestidade)
- Per-key real — hardware não tem
- Curva de ventoinha customizada — o `facer` só tem auto/turbo. O Linuwu-Sense tem `fan_speed` 0–100;
  dá pra portar, mas é um projeto à parte e **mexer nisso pode cozinhar o notebook**.

---

## 5. Roadmap em fases

| Fase | Entrega | Por quê primeiro |
|---|---|---|
| **0** | Fork do `facer` → `turbo` em sysfs + quirk PH315-54 com `predator_v4` | destrava turbo e RPM; sem isso nada do resto existe |
| **1** | `pulsedeckd` + CLI nova (substitui o `acer-rgb`) | separa privilégio de UI; já dá pra usar no dia a dia |
| **2** | GUI com zonas, temas, brilho, turbo e RPM | é o MVP publicável |
| **3** | Efeitos por software + pintar tecla a tecla | é o diferencial |
| **4** | Empacotar: deb/PPA → snap classic → flatpak | distribuição |
| **5** | Mandar PR do patch do módulo pro projeto original | devolve pra comunidade, e tira o fork das suas costas |

---

## 6. Decisões que preciso de você

1. **Stack da GUI** — GTK4/libadwaita (nativo, melhor pra Snap Store, já está instalado) ou Electron
   (você já domina, mas pesa ~150 MB e fica deslocado numa app de sistema)?
2. **Qual cara** — mockup A, B, C ou D (ou um híbrido: B como janela principal + C no tray)?
3. **Nome** do projeto.
4. **Fork ou Linuwu-Sense** — confirma o caminho A?
5. **Escopo do turbo** — só ligar/desligar (seguro) ou também controle manual de ventoinha (arriscado)?

---

## 7. A sua parte (antes de eu começar a codar)

1. Decidir os 5 itens acima.
2. Criar o repo público no GitHub (`LeandroDukievicz/<nome>`) e me dizer o nome.
3. Criar a conta de developer no Snapcraft (snapcraft.io/account) — leva uns minutos e precisa
   de Ubuntu One. Só pra reservar o nome do snap enquanto ainda está livre.
4. Confirmar se posso mexer no `/etc/modprobe.d/acer-rgb.conf` e trocar o DKMS `facer` pelo fork —
   eu mantenho o rollback pronto (`acer-rgb-uninstall` + o DKMS atual intacto).

---

## Fontes
- Módulo atual: https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module
- Linuwu-Sense: https://github.com/0x7375646F/Linuwu-Sense
- Snap custom-device: https://snapcraft.io/docs/reference/interfaces/custom-device-interface/
- Snap confinement: https://snapcraft.io/docs/snap-confinement
