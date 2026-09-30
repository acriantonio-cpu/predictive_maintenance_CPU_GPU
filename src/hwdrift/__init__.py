# SPDX-License-Identifier: Apache-2.0
"""HWDrift: monitor locale della deriva termica di CPU e GPU.

Il pacchetto e' diviso in due metà che non devono mescolarsi:

* lato *collector* (residente, leggero): ``model``, ``channels``, ``config``,
  ``collectors``, ``quality``, ``storage.writer``, ``runner``. Non importa numpy/scipy.
* lato *analisi* (worker a intervalli): ``context``, ``indicators``, ``spc``,
  ``analysis``, ``diagnosis``, ``reporting``. Puo' usare numpy/scipy.
"""

__version__ = "0.1.0.dev0"
