#!/usr/bin/env python3
"""Entrada do daemon, rodando direto do diretório do projeto."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from controlfanrgb.daemon import main  # noqa: E402

sys.exit(main())
