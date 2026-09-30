# SPDX-License-Identifier: Apache-2.0
"""Interfaccia grafica (tkinter, libreria standard: nessuna dipendenza aggiuntiva).

``data.py`` non importa tkinter ed è testabile ovunque; ``widgets.py`` e ``app.py`` sono la
vista. La GUI non legge mai i sensori: mostra ciò che il collector pubblica (``live.json``,
ogni secondo, solo finché la GUI è aperta) e ciò che è nel database.
"""
