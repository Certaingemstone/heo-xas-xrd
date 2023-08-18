# Jade Chongsathapornpong, August 2023
# fdmgen.py
# Script to browse CIF files and add them to an FDMNES calculation.
# Should be placed in the same directory where the corresponding fdmfile is to be made.
# Requires fdmgen-config.txt to be in the same directory as well.
# Intended to be run on Windows machine targeting Windows (UNIX = False) or Linux (UNIX True) compute

CONFIG_PARAMS = ('UNIX', 'INPUT_DIR', 'OUTPUT_DIR', 'RADIUS', 'GREEN', 'SCF', 'QUADRUPOLE', 'DENSITY', 'OXIDE')
RANGE_DEFAULT = '-30.0 0.1 70.0 1.0 100' 

import os
from pathlib import Path
import re
import wx
import pymatgen.core.periodic_table as table

def get_path(wildcard):
    """Used to open a file selection window."""
    app = wx.App(None)
    style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    dialog = wx.FileDialog(None, 'Open CIF file', wildcard=wildcard, style=style)
    if dialog.ShowModal() == wx.ID_OK:
        path = dialog.GetPath()
    else:
        path = None
    dialog.Destroy()
    return path
    
def read_config() -> dict:
    conf = dict()
    with open('fdmgen-config.txt') as f:
        for line in f:
            key, val = line.split()
            conf[key] = val
    for par in CONFIG_PARAMS:
        assert par in conf.keys()
    return conf
    
def get_cif_composition(path_to_cif) -> str:
    with open(path_to_cif, 'r') as f:
        for line in f:
            match = re.search('_chemical_formula_sum.*', line)
            if match:
                return match[0][21:]
    return None

def get_cif_spgroup(path_to_cif) -> str:
    with open(path_to_cif, 'r') as f:
        for line in f:
            match = re.search('_space_group_name_H-M_alt.*', line)
            if match:
                return match[0][27:]
    return None
     
def write_fdminp(name, path_to_cif, Z_absorber, conf) -> str:
    """Writes an FDMNES input file to use the indicated CIF
       and absorbing species, along with the settings
       defined in fdmgen-config.txt (conf)
       Returns the path that was written to."""
    writepath = os.path.join(conf['INPUT_DIR'], '_'.join((name, str(Z_absorber)))) + '.txt'
    outpath = os.path.join(conf['OUTPUT_DIR'], '_'.join((name, str(Z_absorber))))
    if conf['UNIX'] == 'True':
        outpath = str(Path(outpath).as_posix())
    with open(writepath, 'w') as f:
        f.writelines(['! FDMNES input file generated by fdmgen.py\n\n', 'header\n\n', 'filout\n'])
        f.write(outpath+'\n\n')
        f.writelines(['range\n',RANGE_DEFAULT,'\n\n','radius\n', conf['RADIUS'],'\n\n'])
        if conf['QUADRUPOLE'] == 'True':
            f.write('quadrupole\n\n')
        if conf['DENSITY'] == 'True':
            f.write('density\n\n')
        if conf['SCF'] == 'True':
            f.write('SCF\n\n')
        if conf['GREEN'] == 'True':
            f.write('green\n\n')
        if conf['OXIDE'] == 'True':
            f.write('Rpotmax\n15\n\nFull_atom\n\n')
        cif = str(Path(path_to_cif).as_posix()) if conf['UNIX'] == 'True' else path_to_cif
        f.writelines(['Z_absorber\n', str(Z_absorber),'\n\n','Cif_file\n', cif,'\n\n', 'end'])
    return writepath
           
def archive_fdmfile() -> None:
    """Renames an existing fdmfile based on its last modified timestamp."""
    if os.path.exists('fdmfile.txt'):
        mod_timestamp = os.stat('fdmfile.txt').st_mtime
        archive = f'fdmfile{int(mod_timestamp)}.txt'
        os.rename('fdmfile.txt', archive)
        print("Archived previous fdmfile to", archive)
        
def write_fdmfile(pathlist) -> None:
    """Creates fdmfile.txt from a list of paths to FDMNES input text files."""
    with open('fdmfile.txt', 'w') as f:
        f.write(str(len(pathlist)) + '\n')
        f.writelines(pathlist) 

if __name__ == '__main__':
    conf = read_config()
    archive_fdmfile()
        
    # Confirm place to write FDMNES fdmfile, input and output files
    print("Will write fdmfile to current path:", os.curdir)
    print("Will write FDMNES input files to relative path:", conf['INPUT_DIR'])
    print("Will have FDMNES output files to relative path:", conf['OUTPUT_DIR'])
    
    # Select CIF files and prompt user for CIF-specific settings
    print("\nPlease select a CIF file. Its path must be accessible on the machine where FDMNES will execute.")
    
    adding_files = True
    paths_to_inputs = []
    while adding_files:
        cifpath = os.path.relpath(get_path('*.cif'), start=os.curdir)
        print("\nConsidering:", get_cif_composition(cifpath))
        print("with symmetry:", get_cif_spgroup(cifpath))
        if input("Proceed? y/n: ") != 'y':
            continue
        atominfo = input("enter Z or atomic symbol of absorber atom(s): ")
        try:
            atominfo = int(atominfo)
        except:
            pass
        Z_abs = table.get_el_sp(atominfo).Z
        nom = input("Name the output files that FDMNES will create: ")
        wrote_to = write_fdminp(nom, cifpath, Z_abs, conf)
        if conf['UNIX'] == 'True':
            wrote_to = str(Path(wrote_to).as_posix())
        paths_to_inputs.append(wrote_to + '\n')
        if input("Add another file to calculation? (y/n) ") != 'y':
            adding_files = False
    
    write_fdmfile(paths_to_inputs)