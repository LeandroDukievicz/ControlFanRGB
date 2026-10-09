# Licença do diretório `kernel/`

O conteúdo deste diretório — em especial
`0001-expor-turbo-em-sysfs-e-leitura-de-ventoinha-no-PH315-54.patch` — é uma
obra derivada do módulo
[`facer`](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module),
que por sua vez deriva do `acer-wmi` do kernel Linux. Os dois são
**GPL-2.0-only**, então este diretório também é, por herança:

    SPDX-License-Identifier: GPL-2.0-only

O texto completo está em [`LICENSE`](LICENSE).

O resto do projeto (aplicativo, daemon, tray e CLI) é código próprio, não
derivado do kernel, e está sob a licença MIT — ver [`../LICENSE`](../LICENSE).
A fronteira é esta pasta: nada fora dela é derivado de código GPL.
