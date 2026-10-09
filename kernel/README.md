# Patch do módulo `facer`

O PulseDeck precisa de duas coisas que o módulo
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

## Upstream

A intenção é mandar isso como PR para o projeto original — aí o fork deixa de
ser necessário. Ver fase 5 do roadmap.
