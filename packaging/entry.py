"""PyInstaller 打包入口。"""

import multiprocessing
import sys

multiprocessing.freeze_support()

from livetranslate.app import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0]]  # 打包后忽略 Finder/系统传入的杂项参数
    main()
