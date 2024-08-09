import os
from typing import Tuple
import simfile
from simfile.dir import SimfileDirectory, SimfilePack
from simfile.types import Simfile, Chart

TEST_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def open_test_simfile(name: str) -> Simfile:
    path = os.path.join(TEST_BASE_DIR, 'sims', name)
    return simfile.open(path)
    
def open_test_chart(name: str) -> Tuple[Simfile, Chart]:
    sim = open_test_simfile(name)
    return sim, sim.charts[0]

def open_test_simfile_dir(name: str) -> SimfileDirectory:
    path = os.path.join(TEST_BASE_DIR, 'simfile_dirs', name)
    return SimfileDirectory(path)

def open_test_pack(name: str) -> SimfilePack:
    path = os.path.join(TEST_BASE_DIR, 'packs', name)
    return SimfilePack(path)