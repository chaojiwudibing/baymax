#!/bin/zsh
cd "${0:A:h}"
open "http://127.0.0.1:8848/"
exec python3 server.py
