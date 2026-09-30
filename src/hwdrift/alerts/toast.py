# SPDX-License-Identifier: Apache-2.0
"""Notifica toast di Windows (e fallback su altri sistemi).

Il testo non viene mai interpolato nello script PowerShell: passa tramite variabili
d'ambiente, così un titolo con caratteri speciali non può iniettare comandi.
TODO(M1): verificare la visualizzazione con l'AppUserModelID di PowerShell su
Windows 11 e con Focus Assist attivo (il toast può essere soppresso: per questo
esistono anche lo stato persistente e il report).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$n = $t.GetElementsByTagName('text')
$n.Item(0).AppendChild($t.CreateTextNode($env:HWDRIFT_TITLE)) | Out-Null
$n.Item(1).AppendChild($t.CreateTextNode($env:HWDRIFT_BODY)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($t)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:HWDRIFT_APPID).Show($toast)
"""


def show(title: str, body: str) -> bool:
    """Mostra una notifica; restituisce False se non è stato possibile."""
    title = title[:120]
    body = body[:400]
    env = {**os.environ, "HWDRIFT_TITLE": title, "HWDRIFT_BODY": body, "HWDRIFT_APPID": APP_ID}
    try:
        if sys.platform == "win32":
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                               env=env, capture_output=True, timeout=20, check=False)
            return r.returncode == 0
        exe = shutil.which("notify-send")
        if exe:
            r = subprocess.run([exe, "--app-name=HWDrift", title, body], capture_output=True,
                               timeout=10, check=False)
            return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        log.debug("notifica non mostrata", exc_info=True)
    return False
