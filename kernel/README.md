# Patch do módulo `facer`

> Versão **1.2**. O DKMS `facer-1.1` continua no disco para rollback; o
> `reverter.sh` volta direto ao `1.0` original.


O ControlFanRGB precisa de duas coisas que o módulo
[`facer`](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module)
não entrega:

1. **Turbo acessível do userspace.** O `acer_toggle_turbo()` só era alcançável
   pelo handler da tecla física do chassi (`WMID_GAMING_TURBO_KEY_EVENT`,
   `key_num == 0x4`). O patch expõe `/sys/devices/platform/acer-wmi/turbo`
   (leitura e escrita, `0`/`1`), reaproveitando a função que já existia.

2. **Leitura de RPM no PH315-54.** O `ACER_CAP_FAN_SPEED_READ` só é ligado pela
   quirk `predator_v4`. A quirk do PH315-54 não a tinha, e usar o parâmetro de
   módulo `predator_v4=1` **substitui** a quirk inteira — você ganha a leitura
   e perde o turbo. O patch adiciona `.predator_v4 = 1` dentro da quirk do
   PH315-54, então as duas capabilities convivem.

   Isso foi validado no hardware: CPU 3061 → 5555 rpm e GPU 3488 → 5769 rpm ao
   ligar o turbo, voltando aos valores originais ao desligar.

Não há conflito entre as duas: a tecla de turbo é a `key_num 0x4` e a de perfil
térmico é a `0x5`, tratadas separadamente.

3. **Desligar o timeout de backlight do firmware.** O firmware apaga o
   backlight depois de ~30 s sem tecla pressionada, e as escritas de cor por
   WMI **não** resetam esse contador: um efeito rodando a 30 fps continua
   escrevendo com o teclado apagado, e qualquer tecla acende de volta na
   hora. Era a causa de "acende e apaga sozinho" que nenhuma configuração do
   app resolvia. O patch expõe
   `/sys/devices/platform/acer-wmi/backlight_timeout` (0/1).

   Vai por `WMID_GUID3`, método 1 (set) e 2 (get) — GUID que o `facer` já usa
   para outras coisas, mas com um `u64` cru em vez da struct dos helpers
   existentes. Os valores de comando são os mesmos que o Linuwu-Sense usa.

   Uma ressalva na leitura: antes de a opção ter sido escrita alguma vez, o
   PH315-54 responde `0x1E0000000000` — o `0x1E` são os 30 segundos, sem o
   flag `0x80000` que os valores escritos carregam. Em vez de falhar a leitura
   numa máquina que nunca foi configurada, o campo de segundos vale como
   verdade. Depois de uma escrita explícita, o firmware passa a responder as
   constantes documentadas.

   Medido: a configuração mora na EC e **sobrevive à recarga do módulo**.

## Aplicar

```bash
sudo ./instalar.sh
```

Cria `/usr/src/facer-1.1` a partir do `facer-1.0` já instalado, aplica o patch,
registra no DKMS e troca o módulo ativo. O `facer-1.0` continua no disco.

## Reverter

```bash
sudo ./reverter.sh
```

## Licença

GPL-2.0-only, por herança do `facer`/`acer-wmi`. Ver [`LICENSE.md`](LICENSE.md).

## Upstream

O patch foi preparado para o projeto original em **dois PRs separados**, porque
são mudanças de risco bem diferente:

1. **`turbo-sysfs`** — o atributo `/sys/devices/platform/acer-wmi/turbo`.
   Independente de modelo. Supera o [PR #173][pr173] do upstream, que é
   somente leitura, cria um kobject solto em `/sys/devices/platform/fan` e
   reescreve o `module_init` num wrapper que vaza se o segundo init falhar.
2. **`ph315-54-fan-read`** — `.predator_v4 = 1` na quirk do PH315-54.
   Específico do modelo, e arrasta `ACER_CAP_PLATFORM_PROFILE` junto com a
   leitura de ventoinha.

Os dois foram compilados e carregados isoladamente em cima do `main` do
upstream, para provar que não dependem um do outro: com só o primeiro, o
atributo `turbo` aparece e o `hwmon acer` não.

Duas correções em relação ao patch local ao preparar o upstream:

- O `#include <linux/kstrtox.h>` passou a ser guardado com `RTLNX_VER_MIN(5,
  19, 0)` (antes de 5.19 o `kstrtobool()` vinha do `linux/kernel.h`) e foi
  movido para **depois** do `#include <linux/version.h>`. Um guard de versão no
  primeiro bloco de includes avaliaria falso em todo kernel, porque ali o
  `LINUX_VERSION_CODE` ainda não existe.
- Comentários reescritos em inglês e sem referência a este projeto.

[pr173]: https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module/pull/173
