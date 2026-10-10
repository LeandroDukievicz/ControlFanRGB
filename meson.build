project(
  'controlfanrgb',
  version: '0.1.0',
  license: 'MIT',
  meson_version: '>= 1.0.0',
)

python = import('python').find_installation('python3')

prefix     = get_option('prefix')
bindir     = prefix / get_option('bindir')
datadir    = prefix / get_option('datadir')
libexecdir = prefix / get_option('libexecdir')
pkgdatadir = datadir / meson.project_name()
moduledir  = pkgdatadir / 'controlfanrgb'

# Em Debian/Ubuntu estes caminhos são sempre sob o prefixo; mantê-los
# derivados dele é o que faz o DESTDIR do empacotamento funcionar sem truque.
systemd_systemdir = prefix / 'lib' / 'systemd' / 'system'
systemd_userdir   = prefix / 'lib' / 'systemd' / 'user'
udev_rulesdir     = prefix / 'lib' / 'udev' / 'rules.d'

app_id   = 'io.github.leandrodukievicz.ControlFanRGB'
bus_name = app_id + '1'

# ------------------------------------------------------------------ módulo --
# O pacote Python é privado do aplicativo, então vive em /usr/share e os
# executáveis o colocam no sys.path. Isso o desacopla da versão do Python
# instalada, que é o que quebra um /usr/lib/python3.X/dist-packages quando a
# distribuição troca de interpretador.
install_data(
  [
    'controlfanrgb/__init__.py',
    'controlfanrgb/app.py',
    'controlfanrgb/audio.py',
    'controlfanrgb/client.py',
    'controlfanrgb/config.py',
    'controlfanrgb/daemon.py',
    'controlfanrgb/effects.py',
    'controlfanrgb/hardware.py',
    'controlfanrgb/idle.py',
    'controlfanrgb/keyboardview.py',
    'controlfanrgb/perkey.py',
    'controlfanrgb/themes.py',
    'controlfanrgb/tray.py',
    'controlfanrgb/window.py',
  ],
  install_dir: moduledir,
)

# build_info.py não entra na lista acima: a versão do repositório tem valores
# de desenvolvimento e é substituída por esta, gerada com os caminhos reais.
build_info = configuration_data()
build_info.set('VERSION', meson.project_version())
build_info.set('GUI_COMMAND', bindir / 'controlfanrgb')
configure_file(
  input: 'controlfanrgb/build_info.py.in',
  output: 'build_info.py',
  configuration: build_info,
  install: true,
  install_dir: moduledir,
)

# ------------------------------------------------------------ executáveis --
foreach entry : [
  ['controlfanrgb',       'app',    bindir],
  ['controlfanrgbd',      'daemon', libexecdir],
  ['controlfanrgb-tray',  'tray',   libexecdir],
]
  conf = configuration_data()
  conf.set('PYTHON', python.full_path())
  conf.set('PKGDATADIR', pkgdatadir)
  conf.set('MODULE', entry[1])
  configure_file(
    input: 'controlfanrgb.in',
    output: entry[0],
    configuration: conf,
    install: true,
    install_dir: entry[2],
    install_mode: 'rwxr-xr-x',
  )
endforeach

# ----------------------------------------------------------------- dados --
units = configuration_data()
units.set('LIBEXECDIR', libexecdir)
units.set('BUS_NAME', bus_name)

configure_file(
  input: 'data/controlfanrgbd.service',
  output: 'controlfanrgbd.service',
  configuration: units,
  install: true,
  install_dir: systemd_systemdir,
)

configure_file(
  input: 'data/controlfanrgb-tray.service',
  output: 'controlfanrgb-tray.service',
  configuration: units,
  install: true,
  install_dir: systemd_userdir,
)

configure_file(
  input: 'data/@0@.service.in'.format(bus_name),
  output: bus_name + '.service',
  configuration: units,
  install: true,
  install_dir: datadir / 'dbus-1' / 'system-services',
)

install_data(
  'data/@0@.conf'.format(bus_name),
  # /usr/share é o lugar da política que vem do pacote; /etc fica livre para
  # o administrador sobrepor.
  install_dir: datadir / 'dbus-1' / 'system.d',
)

install_data('data/99-controlfanrgb.rules', install_dir: udev_rulesdir)
install_data('data/@0@.desktop'.format(app_id),
             install_dir: datadir / 'applications')
install_data('data/@0@.metainfo.xml'.format(app_id),
             install_dir: datadir / 'metainfo')

icondir = datadir / 'icons' / 'hicolor'
install_data('data/icons/scalable/@0@.svg'.format(app_id),
             install_dir: icondir / 'scalable' / 'apps')
install_data('data/icons/symbolic/@0@-symbolic.svg'.format(app_id),
             install_dir: icondir / 'symbolic' / 'apps')

# Variante simplificada para tamanhos pequenos. O ícone grande tem oito
# colunas de teclas que a 24 px viram uma mancha; esta tem quatro blocos, um
# por zona. O GTK prefere o diretório de tamanho fixo quando ele existe.
foreach tamanho : ['16x16', '22x22', '24x24', '32x32']
  install_data('data/icons/small/@0@.svg'.format(app_id),
               install_dir: icondir / tamanho / 'apps')
endforeach

meson.add_install_script('meson_post_install.py')
