#!/usr/bin/env python3
"""Run inside the provided virtual environment, or use Start_IRBQ_Lab.cmd."""
import os
# Keep linear algebra from occupying every desktop core during interactive work.
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(key,'1')
from irbq.gui import launch
import sys
if __name__=='__main__':
    launch(sys.argv[1] if len(sys.argv)>1 else None)
