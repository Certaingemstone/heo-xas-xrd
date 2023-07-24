"""
Struct2XAS: convert CIFs and XYZs files to FDMNES and FEFF inputs
Developed by Beatriz G. Foschiani, modified by Jade Chongsathapornpong
"""
# main imports
import os

# import logging
import larch.utils.logging as logging
import time
import tempfile
import numpy as np
import pandas as pd
from pandas.io.formats.style import Styler

# pymatgen
from pymatgen.core import Structure, Element, Lattice
from pymatgen.io.xyz import XYZ
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.local_env import CrystalNN
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import (
    LocalGeometryFinder,
)
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import (
    LightStructureEnvironments,
)
from pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies import (
    #SimplestChemenvStrategy,
    MultiWeightsChemenvStrategy,
    #WeightedNbSetChemenvStrategy,
)

from pymatgen.ext.matproj import _MPResterLegacy

# others
import py3Dmol
from larch.math import convolution1D
from larch.io import read_ascii


__author__ = ["Beatriz G. Foschiani", "Mauro Rovezzi"]
__email__ = ["beatrizgfoschiani@gmail.com", "mauro.rovezzi@esrf.fr"]
__version__ = "2023.1.dev"

# initialize the logger
logger = logging.getLogger("struct2xas", level="INFO")


def get_timestamp() -> str:
    """return a custom time stamp string: YYY-MM-DD_HHMM"""
    return "{0:04d}-{1:02d}-{2:02d}_{3:02d}{4:02d}".format(*time.localtime())


def xyz2struct(molecule):
    """Convert pymatgen molecule to dummy pymatgen structure"""

    # Set the lattice dimensions in each direction
    for i in range(len(molecule)-1): 
        if molecule.cart_coords[i][0] > molecule.cart_coords[i+1][0]:
            a = molecule.cart_coords[i][0] 

    for i in range(len(molecule)-1): 
        if molecule.cart_coords[i][1] > molecule.cart_coords[i+1][1]:
            b = molecule.cart_coords[i][1]

    for i in range(len(molecule)-1): 
        if molecule.cart_coords[i][2] > molecule.cart_coords[i+1][2]:
            c = molecule.cart_coords[i][2]

    # Set the lattice dimensions in each direction
    lattice = Lattice.from_parameters(a=a , b=b , c=c , alpha=90, beta=90, gamma=90)
     
    # Create a list of species
    species = [Element(sym) for sym in molecule.species]

    # Create a list of coordinates
    coords = molecule.cart_coords

    # Create the Structure object
    struct = Structure(lattice, species, coords, coords_are_cartesian=True)
    return struct


class Struct2XAS:
    """Class to convert data from CIF and XYZ files to FDMNES and FEFF inputs"""

    def __init__(self, file, abs_atom) -> None:
        """

        Args:
        file (str)  : Path to cif or xyz files.

        abs_atom (str): Absorber element in the structure considering XANES/EXAFS analysis.
                        e.g.: "Fe", "Ni".

        radius (float)  : Cluster radius [Angstrom] to perform FDMNES simulation.


        *NOTES*
        --> IMPORTANT: <--

        for xyz files:
            Structures from xyz files are always consider no-symmetric for the lack of information.
            For creating the object from an XYZ file, a no-symmetry pymatgen structure is generated
            (spacegroup: P1).
            The lattice parameters chosen for this structure are arbitrary and are based on the size
            of the molecule, as are the fractional coordinates.
            Therefore, the analysis of this structure is limited to the central atoms and is not
            valid for atoms near the edges of the molecule.

        for cif files:
            For creating the object from cif file, a pymatgen structure is generated with symmetry
            infomation from cif file.
        """

        self.file = file
        self.abs_atom = abs_atom
        self.frame = 0
        self.abs_site = 0
        self._structure_reader()
        self.nabs_sites = len(self.get_abs_sites())
        self.elems = self._get_elems()
        self.species = self._get_species()

        logger.info(
            f"Frames: {self.nframes}, Absorbing sites: {self.nabs_sites}. (Indexes for frames and abs_sites start at 0)"
        )

    def set_frame(self, frame=0):
        """For multiframe xyz file, set the frame index site."""
        self.frame = frame
        if self.molecules is not None:
            self.struct = xyz2struct(self.molecules[self.frame])
            self.mol = self.molecules[self.frame]
        else:
            logger.error("single frame structure")
        logger.debug(f"frame idx: {frame} ")

    def get_frame(self):
        """For multiframe xyz file, get the frame index site."""
        return self.frame

    def set_abs_site(self, abs_site=0):
        """Set the crystallographic index site for the absorbing atom."""
        try:
            self.get_abs_sites()[abs_site]
        except IndexError:
            logger.error("absorber site index out of range")
            raise IndexError("absorber site index out of range")
        logger.debug(f"abs_site idx: {abs_site} ")
        self.abs_site = abs_site

    def get_abs_site(self):
        """Get the crystallographic index site for the absorbing atom."""
        return self.abs_site

    def _get_elems(self):
        """Get elements present in the structure"""
        elems_list = []
        for _, elem in enumerate(self.struct):
            # if self.is_cif:
            for e in elem.species.elements:
                if e.name not in elems_list:
                    elems_list.append(e.name)

            # if self.is_xyz:
            #     if elem.species_string not in elems_list:
            #         elems_list.append(elem.species_string)

        return elems_list

    def _get_species(self):
        """Get elements present in the structure"""
        species_list = []
        species_list_occu = []
        for _, elem in enumerate(self.struct):
            if not self.full_occupancy:
                if str(elem.species) not in species_list_occu:
                    species_list_occu.append(str(elem.species))
            self.atoms_occu = species_list_occu

            for e in elem.species.elements:
                if str(e) not in species_list:
                    species_list.append(str(e))

        return species_list

    def _structure_reader(self):
        """Reader to initialize the structure/molecule from the input file"""

        self.is_cif = False
        self.is_xyz = False

        # Split the file name and extension
        if os.path.isfile(self.file):
            # file_dirname = os.path.dirname(file)
            file = os.path.basename(self.file)
            split_file = os.path.splitext(file)
            self.file_name = split_file[0]
            ext = split_file[1]
        else:
            errmsg = f"{self.file} not found"
            logger.error(errmsg)
            raise FileNotFoundError(errmsg)

        if ext == ".cif":
            self.is_cif = True
            self.xyz = None
            self.molecules = None
            self.mol = None
            self.nframes = 1
            self.struct = Structure.from_file(self.file)
            logger.debug("structure creation from a CIF file")
        elif ext == ".xyz":
            self.is_xyz = True
            self.xyz = XYZ.from_file(self.file)
            self.molecules = self.xyz.all_molecules
            self.mol = self.molecules[self.frame]
            self.nframes = len(self.molecules)
            self.struct = xyz2struct(self.mol)
            logger.debug("structure creation from a XYZ file")
        else:
            errmsg = "only CIF and XYZ files are currently supported"
            logger.error(errmsg)
            raise NotImplementedError(errmsg)

    def get_abs_sites(self):
        """Get information about the possible absorbing sites present in the structure.
        If the structure has a readable symmetry given by a cif fichier, the method will return
        just equivalent sites.
        If the structure does not have symmetry or the symmetry is not explicit in the files, this
        method will return
        all possible sites for absorber atoms.

        return a list of lists. The lists inside the list contain the following respective
        information:

            > absorber index:   The absorber index is the index that identifies the absorber site.
                                To change the absorber site being analyzed,
                                the absorber index must be set using the method set_abs_site().

            > specie:           The specie for absorber sites.

            > frac. coord.:     Fractionnal coodinatite position for absorber sites.
                                If the structure was created using xyz file, the frac. coords.
                                are arbitrary and the lattice parameters are based on the molecule
                                size.

            > wyckoff site:     Wyckoff site for absorber sites. For structures created from xyz
                                files, Wyckoff sites are always equal to 1a. (No symmetry)

            > cart_coords:      Cartesian coordinate position for absorber sites.

            > occupancy:        Occupancy for absorber sites. For structures created from xyz files,
                                occupancy are always equal to 1.

            > structure index:  Original index for absorber atoms in pymatgen structure. (Not
                                necessary for public methods)
        """

        abs_sites = []
        if self.is_cif:
            sym_struct = SpacegroupAnalyzer(self.struct).get_symmetrized_structure()

            def _get_idx_struct(sym_site):
                """get the index of the absorbing atom corresponding to the list of atoms in struct"""
                for idx, atom in enumerate(self.struct):
                    if np.allclose(atom.coords, sym_site[4], atol=0.01) is True:
                        return idx

            # Get multiples sites for absorber atom
            for idx, sites in enumerate(sym_struct.equivalent_sites):
                sites = sorted(
                    sites, key=lambda s: tuple(abs(x) for x in s.frac_coords)
                )
                site = sites[0]
                abs_row = [idx, site.species_string]
                abs_row.append([j for j in np.round(site.frac_coords, 4)])
                abs_row.append(sym_struct.wyckoff_symbols[idx])
                abs_row.append(np.array([j for j in np.round(site.coords, 4)]))
                if self.abs_atom in abs_row[1]:
                    try:
                        ats_occ = abs_row[1].split(",")
                        at_occ = [at for at in ats_occ if self.abs_atom in at][0]
                        occupancy = float(at_occ.split(":")[1])
                        self.full_occupancy = False
                    except Exception:
                        occupancy = 1
                        self.full_occupancy = True
                    abs_row.append(occupancy)
                    abs_row.append(_get_idx_struct(abs_row))
                    abs_sites.append(abs_row)

        if self.is_xyz:
            self.full_occupancy = True
            k = 0
            for idx, elem in enumerate(self.struct):
                if f"{self.abs_atom}" in elem:
                    abs_sites += [
                        (
                            int(f"{k}"),
                            (str(elem.specie)) + f"{k}",
                            "-",
                            "-",
                            elem.coords.round(4),
                            1,
                            idx,
                        )
                    ]
                    k += 1
        if len(abs_sites) == 0:
            logger.error(" ---- Absorber site not found ---- ")
            raise AttributeError("Absorber atom not found in structure")
        return abs_sites

    def get_abs_sites_info(self):
        """Get abs sites info and return pandas.DataFrame.

        return pandas.DataFrame:

            > idx_abs:      The absorber index is the index that identifies the absorber site.
                            To change the absorber site being analyzed, the absorber index must
                            be set using the method set_abs_site().

            > specie:       The specie for absorber sites.

            > frac_coords.: Fractionnal coodinatite position for absorber sites.
                            If the structure was created using xyz file, the frac. coords. are
                            arbitrary and the lattice param are is a=b=c=1


            > wyckoff_site: Wyckoff site for absorber sites. For structures created from xyz
                            files, Wyckoff sites are always equal to 1a. (No symmetry)

            > cart_coords:  Cartesian coordinate position for absorber sites.

            > occupancy:    Occupancy for absorber sites. For structures created from xyz files,
                            occupancy are always equal to 1.

            > idx_struct:   Original index for absorber atoms in pymatgen structure. (Not necessary
                            for public methods)
        """

        abs_sites = self.get_abs_sites()
        df = pd.DataFrame(
            abs_sites,
            columns=[
                "idx_abs",
                "specie",
                "frac_coords",
                "wyckoff_site",
                "cart_coords",
                "occupancy_abs_atom",
                "idx_struct",
            ],
        )
        df = Styler(df).hide(axis="index")
        return df

    def get_atoms_from_abs(self, radius):
        """Get atoms in sphere from absorbing atom with certain radius"""
        abs_sites = self.get_abs_sites()

        if self.is_cif:
            nei_list = self.struct.get_sites_in_sphere(
                abs_sites[self.abs_site][4], float(radius)
            )  # list os neighbors atoms in sphere
            sites = []

            for i in range(len(nei_list)):
                nei_list[i].cart_coords = (
                    nei_list[i].coords - abs_sites[self.abs_site][4]
                )

            for i, _ in enumerate(nei_list):
                if np.allclose(nei_list[i].cart_coords, [0, 0, 0], atol=0.01) is True:
                    sites.append(
                        [
                            nei_list[i],
                            f"{self.abs_atom}(abs)",
                            0.000,
                            {f"{self.abs_atom}(abs)": 1},
                        ]
                    )
                    nei_list.remove(nei_list[i])

            for i in range(len(nei_list)):
                occu_dict = dict(nei_list[i].as_dict()["species"])
                sites += [
                    [
                        nei_list[i],
                        str(nei_list[i].species.elements[0]),
                        round(np.linalg.norm(nei_list[i].cart_coords - [0, 0, 0]), 5),
                        occu_dict,
                    ]
                ]
        if self.is_xyz:
            nei_list = self.mol.get_sites_in_sphere(
                abs_sites[self.abs_site][4], float(radius)
            )  # list os neighbors atoms in sphere
            sites = []

            for i in range(len(nei_list)):
                nei_list[i].cart_coords = (
                    nei_list[i].coords - abs_sites[self.abs_site][4]
                )

            for i, _ in enumerate(nei_list):
                if np.allclose(nei_list[i].cart_coords, [0, 0, 0], atol=0.01) is True:
                    sites.append([nei_list[i], f"{self.abs_atom}(abs)", 0.000])
                    nei_list.remove(nei_list[i])

            sites += [
                [
                    nei_list[i],
                    nei_list[i].species_string,
                    round(np.linalg.norm(nei_list[i].cart_coords - [0, 0, 0]), 5),
                ]
                for i in range(len(nei_list))
            ]

        sites = sorted(sites, key=lambda x: x[2])
        return sites

    def get_coord_envs(self):
        """
        For structures from cif files, this method will try to find the coordination environment
        type and return the elements and the coordination env. symbol from the first using the
        classes from pymatgen as LocalGeometryFinder(), BVAnalyzer(), MultiWeightsChemenvStrategy()
        and LightStructureEnvironments() .

            > coordination env. symbol.
                        S:4 - Square Plane
                        T:4 - Tetrahedral
                        T:5 - Trigonal bipyramid
                        S:5 - Square pyramidal
                        O:6 - Octahedral
                        T:6 - Trigonal prism
            > ce_fraction:
                        probability for given coordination env. (between 0 and 1)

            > CSM:
                        a measure of the degree of symmetry in the coordination environment.
                        It is based on the idea that symmetric environments are more stable
                        than asymmetric ones, and is calculated using a formula that takes
                        into account the distances and angles between the coordinating atoms.
                        The CSM can be understood as a distance to a shape and can take values
                        between 0.0 (if a given environment is perfect) and 100.0 (if a given
                        environment is very distorted). The environment of the atom is then
                        the model polyhedron for which the similarity is the highest, that is,
                        for which the CSM is the lowest.

            > permutation:
                        possible permutation of atoms surrounding the central atom.
                        This is a list that indicates the order in which the neighboring atoms
                        are arranged around the central atom in the coordination environment.
                        The numbering starts from 0, and the list indicates the indices of the
                        neighboring atoms in this order. For example, in the second entry of the
                        list above, the permutation [0, 2, 3, 1, 4] means that the first
                        neighboring atom is in position 0, the second is in position 2, the
                        third is in position 3, the fourth is in position 1, and the fifth is
                        in position 4. The permutation is used to calculate the csm value.

            > site:
                        element in the coordination environment and its coordinates (cartesian and
                        fractional).

            > site_index:
                        structure index for the coordinated atom.


        For structures from the xyz file the methods will try to return the elements (but not the
        coord. env. symbol) for the first coordination env. shell
        using the the class CrystalNN() from pymatgen.

        List of lists:

            [0]: Info about which site is being analyzed.

            [1]: Coord. env as dictionary.

            [2]: Info about coord. env.
                > site:
                    element in the coordination environment and its coordinates (cartesian and
                    fractional).

                > image:
                    image is defined as displacement from original site in structure to a given site.
                    i.e. if structure has a site at (-0.1, 1.0, 0.3), then (0.9, 0, 2.3) ->
                    jimage = (1, -1, 2).
                    Note that this method takes O(number of sites) due to searching an original site.

                > weight:
                    quantifies the significance or contribution of each coordinated site to the
                    central site's coordination.

                > site_index:
                    structure index for the coerdinated atom.


        """
        abs_sites = self.get_abs_sites()
        idx_abs_site = abs_sites[self.abs_site][-1]

        if self.is_cif:
            lgf = LocalGeometryFinder()
            lgf.setup_structure(self.struct)

            bva = BVAnalyzer()  # Bond Valence Analyzer
            try:
                valences = bva.get_valences(structure=self.struct)
            except ValueError:
                valences = "undefined"

            coord_env_list = []
            se = lgf.compute_structure_environments(
                max_cn=6,
                valences=valences,
                only_indices=[idx_abs_site],
                only_symbols=["S:4", "T:4", "T:5", "S:5", "O:6", "T:6"],
            )

            dist_1st_shell = se.voronoi.neighbors_distances[idx_abs_site][0]["max"]
            logger.debug(dist_1st_shell)
            strategy = MultiWeightsChemenvStrategy.stats_article_weights_parameters()
            # strategy = SimplestChemenvStrategy(distance_cutoff=1.1, angle_cutoff=0.3)
            lse = LightStructureEnvironments.from_structure_environments(
                strategy=strategy, structure_environments=se
            )
            coord_env_ce = lse.coordination_environments[idx_abs_site]
            ngbs_sites = lse._all_nbs_sites
            coord_env_list.append(
                [
                    f"Coord. Env. for Site {abs_sites[self.abs_site][0]}",
                    coord_env_ce,
                    ngbs_sites,
                ]
            )

        if self.is_xyz:
            obj = CrystalNN()
            coord_env_list = []
            coord_env = obj.get_nn_info(self.struct, idx_abs_site)
            for site in coord_env:
                site["site"].cart_coords = self.struct[site["site_index"]].coords
            coord_dict = obj.get_cn_dict(self.struct, idx_abs_site)
            coord_env_list.append(
                [
                    f"Coord. Env. for Site {abs_sites[self.abs_site][0]}",
                    {"ce_symbol": f"Elements Dict = {coord_dict}"},
                    coord_env,
                ]
            )

        return coord_env_list

    def get_coord_envs_info(self):
        """
        Class with summarized and more readable information from get_coord_envs() method
        """

        coord_env = self.get_coord_envs()[0]
        abs_site_coord = self.get_abs_sites()[self.abs_site][4]

        elems_dist = []
        for site in coord_env[2]:
            if self.is_cif:
                coord_sym = [
                    coord_env[1][i]["ce_symbol"] for i in range(len(coord_env[1]))
                ]
                elems_dist.append(
                    (
                        site["site"].species,
                        round(np.linalg.norm(site["site"].coords - abs_site_coord), 5),
                    )
                )
            if self.is_xyz:
                coord_sym = coord_env[1]["ce_symbol"]
                elems_dist.append(
                    (
                        site["site"].species,
                        round(
                            np.linalg.norm(site["site"].cart_coords - abs_site_coord), 5
                        ),
                    )
                )
        elems_dist = sorted(elems_dist, key=lambda x: x[1])
        df = pd.DataFrame(data=elems_dist, columns=["Element", "Distance"])
        print(
            f"Coord. Env. from absorber atom: {self.abs_atom} at site {self.get_abs_site()}\n(For more details use get_coord_envs() method) "
        )
        return coord_sym, df

    def make_input_fdmnes(
        self,
        radius,
        parent_path=None,
        output_path=None,
        name=None,
        template=None,
        green=True,
        **kwargs,
    ):
        """
        Create a fdmnes input from a template.

        Args:

            > radius (float):
                        radius for fdmnes calculation [Angstrom].
                        
            > parent_path (str):
                        Path to where the fdmfile will be created.
                        if None will create a relative path automatically.

            > output_path (str):
                        Path to where the input files will be created.
                        if None will create a relative path automatically, the same as parent_path.
                        
            > output_name (str):
                        Output file name; if None will be job_inp.

            > green (boolean):
                        if True, both green AND SCF methods are used.
                        if False, just the SCF method is used (more time for calculation).

            NOTE: for further information about FDMNES keywords, search for "FDMNES user's guide"


        return fdmnes input.
        """
        replacements = {}
        replacements.update(**kwargs)

        if template is None:
            template = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "templates", "fdmnes.tmpl"
            )

        if parent_path is None:
            tmpdir = tempfile.mkdtemp(prefix="struct2xas-")
            parent_path = os.path.join(tmpdir, "fdmnes", self.file_name, self.abs_atom, f"site{self.abs_site}")
        self.parent_path = parent_path
        
        if output_path is None:
            output_path = self.parent_path
        
        if name is None:
            name = 'job_inp'

        if green:
            method = "green"
        else:
            method = ""

        absorber = ""
        crystal = ""
        occupancy = ""

        if self.is_cif:
            try:
                selected_site = self.get_abs_sites()[self.abs_site]
            except IndexError:
                print("IndexError: check if abs_atom is correct")

            if not selected_site[-2] == 1:
                logger.warning("the selected site does not have full occupancy!")

            # SpacegroupAnalyzer to get symmetric structure
            analyzer = SpacegroupAnalyzer(self.struct)
            structure = analyzer.get_refined_structure()

            symmetry_data = analyzer.get_symmetry_dataset()
            group_number = symmetry_data["number"]
            group_choice = symmetry_data["choice"]

            # FDMNES doesn't recognize 2 as a space group.
            if group_number == 2:
                group_number = "P-1"

            crystal = f"{crystal}"
            replacements["crystal"] = "crystal"

            group = f"{group_number}"
            if group_choice:
                group += f":{group_choice}"
            replacements["group"] = f"spgroup\n{group}"

            unique_sites = []
            for sites in analyzer.get_symmetrized_structure().equivalent_sites:
                sites = sorted(
                    sites, key=lambda s: tuple(abs(x) for x in s.frac_coords)
                )
                unique_sites.append((sites[0], len(sites)))
                sites = str()
            if self.full_occupancy:
                for i, (site, _) in enumerate(unique_sites):
                    try:
                        e = site.specie
                    except AttributeError:
                        e = Element(site.species_string.split(":")[0])
                    sites += "\n" + (
                        f"{e.Z:>2d} {site.a:12.8f} {site.b:12.8f} {site.c:12.8f}"
                        f" {site.species_string:>4s}"
                    )
            else:
                occupancy = "occupancy"
                for site, _ in unique_sites:
                    for i, e in enumerate(site.species.elements):
                        occu = site.as_dict()["species"][i]["occu"]
                        sites += "\n" + (
                            f"{e.Z:>2d} {site.a:12.8f} {site.b:12.8f} {site.c:12.8f} {occu}"
                            f" {str(e):>4s}"
                        )
            l = structure.lattice
            replacements["lattice"] = (
                f"{l.a:<12.8f} {l.b:12.8f} {l.c:12.8f} "
                f"{l.alpha:12.8f} {l.beta:12.8f} {l.gamma:12.8f}"
            )

            absorber = f"{absorber}"
            for i in range(len(unique_sites)):
                if (
                    np.allclose(unique_sites[i][0].coords, selected_site[4], atol=0.01)
                    is True
                ):
                    replacements["absorber"] = f"absorber\n{i+1}"

            # absorber = f"{absorber}"
            # replacements["absorber"] = f"Z_absorber\n{round(Element(elem).Z)}"

            comment = (
                f"cif file name: {self.file_name}\ncreation date:{get_timestamp()}"
            )

        if self.is_xyz:
            absorber = ""
            crystal = ""
            occupancy = ""

            def make_cluster(radius):
                """
                Create a cluster with absorber atom site at the center.

                Args:
                    > radius (float): Cluster radius [Angstrom].

                return the species and coords for the new cluster structure

                """

                selected_site = self.get_abs_sites()[self.abs_site]
                cluster = self.mol.get_sites_in_sphere(selected_site[-3], radius)

                # showing and storing cartesian coords and species
                atoms = []

                # abs_atom at the cluster center
                for i in range((len(cluster))):
                    try:
                        species = round(Element((cluster[i].specie).element).Z)
                    except AttributeError:
                        species = round(Element(cluster[i].specie).Z)

                    # getting species, after atomic number() and rounding
                    coords = (
                        cluster[i].coords - selected_site[4]
                    )  # cartesial coords and ""frac_coords"" are the same for molecule structure (a = b = c = 1)
                    coords = np.around(coords, 5)
                    dist = round(np.linalg.norm(coords - [0, 0, 0]), 5)
                    atoms.append((species, coords, dist))
                atoms = sorted(atoms, key=lambda x: x[2])
                return atoms

            crystal = f"{crystal}"
            replacements["crystal"] = "molecule"

            a = make_cluster(radius=radius)
            sites = str()
            for i in range(len(a)):
                e = a[i][0]
                c = a[i][1]
                sites += "\n" + (
                    f"{e:>2d} {c[0]:12.8f} {c[1]:12.8f} {c[2]:12.8f}"
                    f" {Element.from_Z(e).name}"
                )

            absorber = f"{absorber}"
            for i in range(len(a)):
                if np.allclose(a[i][1], [0, 0, 0], atol=0.01) is True:
                    replacements["absorber"] = f"absorber\n{i+1}"

            replacements["group"] = ""
        
            replacements["lattice"] = (
                f"{1:<12.8f} {1:12.8f} {1:12.8f} "
                f"{90:12.8f} {90:12.8f} {90:12.8f}"
            )

            comment = (
                f"xyz file name: {self.file_name}\ncreation date:{get_timestamp()}"
            )

        replacements["sites"] = sites
        replacements["radius"] = radius
        replacements["method"] = method
        replacements["comment"] = comment
        replacements["occupancy"] = occupancy   
        
        replacements["jobname"] = name

        try:
            os.makedirs(parent_path, mode=0o755)
        except FileExistsError:
            pass

        # Write the input file.
        filename = os.path.join(output_path, name + '.txt')
        with open(filename, "w") as fp, open(template) as tp:
            inp = tp.read().format(**replacements)
            fp.write(inp)

        # Write the fdmfile.txt.
        with open(os.path.join(parent_path, "fdmfile.txt"), "a") as fp:
            fp.write('\n')
            fp.write(output_path + '/' + name + '.txt')

        logger.info(f"written FDMNES input fdmfile -> {parent_path + '/' + name + '.txt'}")
        logger.info(f"written FDMNES main input -> {filename}")

    def make_input_feff(
        self,
        radius,
        parent_path=None,
        template=None,
        feff_comment="*",
        edge="K",
        sig2=None,
        debye=None,
    ):
        """
        Create a FEFF input from a template.

        Args:

            > radius (float):
                        radius for feff calculation [Angstrom].

            > parent_path (str):
                        path for feff folder creation. If None will create an automatic path from where script is running.

            > feff_coment (str):
                        comment for input file.

            > sig2 (float or None):
                        SIG2 keywork, if None it will be commented

            > debye (list of two floats or None):
                        DEBYE keyword, if None it will be commented else give
                        debye=[temperature, debye_temperature]
                        > temperatue (float):
                            temperature at which the Debye-Waller factors are calculate [Kelvin].
                        > debye_temperature (float):
                            Debye Temperature of the material [Kelvin].

            NOTE: for further information about FEFF keywords, search for "FEFF user's guide"

        return fdmnes input.
        """

        if parent_path is None:
            tmpdir = tempfile.mkdtemp(prefix="struct2xas-")
            parent_path = os.path.join(tmpdir, "feff", self.file_name, self.abs_atom, f"site{self.abs_site}")
        self.parent_path = parent_path

        if template is None:
            template = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "templates",
                "feff_exafs.tmpl",
            )

        if sig2 is None:
            use_sig2 = "*"
            sig2 = 0.005
        else:
            use_sig2 = ""

        if debye is None:
            use_debye = "*"
            temperature, debye_temperature = 0, 0
        else:
            use_debye = ""
            temperature, debye_temperature = debye[0], debye[1]

        replacements = {}
        feff_comment = f"{feff_comment}"
        edge = f"{edge}"
        radius = f"{radius}"
        use_sig2 = f"{use_sig2}"
        sig2 = f"{sig2}"
        use_debye = f"{use_debye}"
        temperature = f"{temperature}"
        debye_temperature = f"{debye_temperature}"

        if self.is_cif:
            sites = self.get_atoms_from_abs(radius)
            ipot_list = [(0, Element(f"{self.abs_atom}").Z, sites[0][1])]
            ipot = {f"{self.abs_atom}(abs)": 0}
            elems = self.species

            for i, elem in enumerate(elems):
                ipot[elem] = i + 1
            for i in range(1, len(sites)):
                for j, _ in enumerate(sites[i][0].species.elements):
                    if str(sites[i][0].species.elements[j]) in elems:
                        ipot_list.append(
                            (
                                ipot[str(sites[i][0].species.elements[j])],
                                sites[i][0].species.elements[j].Z,
                                str(sites[i][0].species.elements[j]),
                            )
                        )
            pot = list(dict.fromkeys(ipot_list))
            potentials = str("* ipot  Z   tag [lmax1 lmax2 xnatph sphinph]")
            for i, _ in enumerate(pot):
                potentials += "\n" + (f"{pot[i][0]:>5} {pot[i][1]:>3} {pot[i][2]:>5}")

            atoms_list = [
                (sites[0][0].cart_coords, 0, sites[0][1], sites[0][2], sites[0][3])
            ]
            for i in range(1, len(sites)):
                atoms_list.append(
                    (
                        sites[i][0].cart_coords,
                        ipot[str(sites[i][0].species.elements[0])],
                        sites[i][1],
                        sites[i][2],
                        sites[i][3],
                    )  # cart, ipot, tag, dist
                )

        if self.is_xyz:
            sites = self.get_atoms_from_abs(radius=radius)
            ipot_list = [(0, Element(f"{self.abs_atom}").Z, sites[0][1])]
            elems = []
            ipot = {}
            for i in range(1, len(sites)):
                if sites[i][0].species_string not in elems:
                    elems.append((sites[i][0].species_string))
            for i, elem in enumerate(elems):
                ipot[elem] = i + 1
            for i in range(1, len(sites)):
                if sites[i][0].species_string in elems:
                    ipot_list.append(
                        (
                            ipot[sites[i][0].species_string],
                            sites[i][0].specie.Z,
                            sites[i][0].species_string,
                        )
                    )
            pot = list(dict.fromkeys(ipot_list))
            potentials = str("* ipot  Z   tag [lmax1 lmax2 xnatph sphinph]")
            for i in range(len(pot)):
                potentials += "\n" + (f"{pot[i][0]:>5} {pot[i][1]:>3} {pot[i][2]:>5}")
            atoms_list = []
            for i in range(len(sites)):
                atoms_list.append(
                    (
                        sites[i][0].cart_coords,
                        ipot_list[i][0],
                        sites[i][1],  # tag
                        sites[i][2],
                    )
                )
        atoms = str(
            "*   x          y          z     ipot   tag    distance   occupancy"
        )
        at = atoms_list
        for i in range(len(at)):
            if self.full_occupancy:
                atoms += "\n" + (
                    f"{at[i][0][0]:10.6f} {at[i][0][1]:10.6f} {at[i][0][2]:10.6f} {  int(at[i][1])}  {at[i][2]:>5} {at[i][3]:10.5f}         *1 "
                )
            else:
                choice = np.random.choice(
                    list(at[i][4].keys()), p=list(at[i][4].values())
                )
                atoms += "\n" + (
                    f"{at[i][0][0]:10.6f} {at[i][0][1]:10.6f} {at[i][0][2]:10.6f} {ipot[choice]}  {choice:>5} {at[i][3]:10.5f} *{at[i][4]}"
                )

        title = f"TITLE {self.file_name}\nTITLE {get_timestamp()}\nTITLE site {self.abs_site}"

        replacements["feff_comment"] = feff_comment
        replacements["edge"] = edge
        replacements["radius"] = radius
        replacements["use_sig2"] = use_sig2
        replacements["sig2"] = sig2
        replacements["use_debye"] = use_debye
        replacements["temperature"] = temperature
        replacements["debye_temperature"] = debye_temperature
        replacements["potentials"] = potentials
        replacements["atoms"] = atoms
        replacements["title"] = title
        # replacements[""] =

        try:
            os.makedirs(parent_path, mode=0o755)
        except FileExistsError:
            pass

        # Write the input file.
        filename = os.path.join(parent_path, "feff.inp")
        with open(filename, "w") as fp, open(template) as tp:
            inp = tp.read().format(**replacements)
            fp.write(inp)

        logger.info(f"written FEFF input in -> {self.parent_path}")

    def _get_xyz_and_elements(self, radius):
        """
        Get information about cartesian coords and elements surrounding the central atom given
        a radius.

         Args:
            > radius(float):
                    radius from the central atom [Angstrom].

         return list of elements with coords and list of elements, both lists of strings.

        """
        sites = self.get_atoms_from_abs(radius)
        coords = []
        elements = []
        for _, site in enumerate(sites):
            try:
                coords.append(
                    (str((site[0].species).elements[0].name), site[0].cart_coords)
                )
            except AttributeError:
                coords.append((str(site[0].specie), site[0].cart_coords))

        output_str = str(len(coords)) + "\n\n"
        for element, coords in coords:
            coords_str = " ".join([f"{c:.6f}" for c in coords])
            output_str += f"{element} {coords_str}\n"
            if element not in elements:
                elements.append(element)
        elements = sorted(elements)
        return output_str, elements

    def _round_up(self, x):
        rounded_x = np.ceil(x * 100) / 100
        return rounded_x

    def visualize(self, radius=2.5, unitcell=False):
        """
        Display a 3D visualization for material local structure.

        Args:
            > radius (float):
                    radius visualization from the central atom.

            > unitcell (boolean):
                    if True, allows the visualization of the structure unit cell.

        return 3D structure visualization from py3Dmol.
        """
        radius = self._round_up(radius)

        xyz, elems = self._get_xyz_and_elements(radius)

        a = self.struct.lattice.a
        b = self.struct.lattice.b
        c = self.struct.lattice.c
        alpha = self.struct.lattice.alpha
        beta = self.struct.lattice.beta
        gamma = self.struct.lattice.gamma
        xyzview = py3Dmol.view(
            width=600, height=600
        )  # http://3dmol.org/doc/GLViewer.html#setStyle
        xyzview.addModel(xyz, "xyz")

        if unitcell is True:
            m = xyzview.getModel()
            m.setCrystData(a, b, c, alpha, beta, gamma)
            xyzview.addUnitCell()

        colors = [
            "red",
            "green",
            "blue",
            "orange",
            "yellow",
            "white",
            "purple",
            "pink",
            "brown",
            "black",
            "gray",
            "cyan",
            "magenta",
            "olive",
            "navy",
            "teal",
            "maroon",
            "turquoise",
            "indigo",
            "salmon",
        ]
        color_elems = {}
        for idx, elem in enumerate(self.elems):
            color_elems[f"{elem}"] = colors[idx]

        for idx, elem in enumerate(elems):
            color = color_elems[f"{elem}"]
            xyzview.setStyle(
                {"elem": f"{elem}"},
                {
                    "stick": {
                        "radius": 0.1,
                        "opacity": 1,
                        "hidden": False,
                        "color": f"{color}",
                    },
                    "sphere": {"color": f"{color}", "radius": 0.4, "opacity": 1},
                },
            )
        xyzview.addLabel(
            "Abs",
            {
                "fontColor": "black",
                "fontSize": 14,
                "backgroundColor": "white",
                "backgroundOpacity": 0.8,
                "showBackground": True,
            },
            {"index": 0},
        )

        xyzview.zoomTo()
        xyzview.show()

        logger.info(color_elems)
        if not self.full_occupancy:
            logger.warning("3D displayed image does not consider partial occupancy")
            logger.info("check atoms occupancy here:", self.atoms_occu)
            # color_elems = {}
            # for idx, elem in enumerate(self.species_occu):
            #     color_elems[f"{list(elem.values())[0]}"] = colors[idx]
            # print("Label:\n", color_elems)


def get_fdmnes_info(file, labels=("energy", "mu")):
    """Get info from the fdmnes output file such as edge energy, atomic number Z,
      and fermi level energy, and returns a group with the storage information

      Parameters:

        file (str): path to the fdmnes output file.
    Obs: The INPUT file must have the "Header" keyword to use this function in the OUTPUT file

    """

    group = read_ascii(file, labels=labels)

    with open(group.path) as f:
        line = f.readlines()[3]
        header = line.split()
        (
            e_edge,
            Z,
            e_fermi,
        ) = (float(header[0]), float(header[1]), float(header[6]))
        print(
            f"Calculated Fermi level: {e_fermi}\nAtomic_number: {Z}\nEnergy_edge: {e_edge}"
        )

    group.e_edge = e_edge
    group.Z = Z
    group.e_fermi = e_fermi

    return group


def convolve_data(
    energy, mu, group, fwhm=1, linbroad=[1.5, 0, 50], kernel="gaussian", efermi=None
):
    """
    Function for manual convolution using Convolution1D from larch and returning a group

    Generic discrete convolution

    Description
    -----------

    This is a manual (not optimized!) implementation of discrete 1D
    convolution intended for spectroscopy analysis. The difference with
    commonly used methods is the possibility to adapt the convolution
    kernel for each convolution point, e.g. change the FWHM of the
    Gaussian kernel as a function of the energy scale.

    Resources
    ---------

    .. [WPconv] <http://en.wikipedia.org/wiki/Convolution#Discrete_convolution>
    .. [Fisher] <http://homepages.inf.ed.ac.uk/rbf/HIPR2/convolve.htm>
    .. [GP1202] <http://glowingpython.blogspot.fr/2012/02/convolution-with-numpy.html>

    """
    conv = convolution1D
    gamma_e = conv.lin_gamma(energy, fwhm=fwhm, linbroad=linbroad)
    mu_conv = conv.conv(energy, mu, kernel=kernel, fwhm_e=gamma_e, efermi=efermi)
    group.conv = mu_conv
    return group


def get_cif(api_key, material_id):
    """
    Function to collect CIF file given the material id from Material Project Database.

    Parameters:
        api_key (str): api-key from Materials Project
        material id (str): material id (format mp-xxxx) from Materials Project

    """
    cif = _MPResterLegacy(api_key).get_data(material_id, prop="cif")
    pf = _MPResterLegacy(api_key).get_data(material_id, prop="pretty_formula")[0][
        "pretty_formula"
    ]
    try:
        os.makedirs("mp-cifs", mode=0o755)
    except FileExistsError:
        pass
    with open(
        file=f"mp-cifs/{pf}_{material_id}.cif",
        mode="w",
    ) as f:
        f.write(cif[0]["cif"])
        return print(f"written cif in mp-cifs/{pf}_{material_id}.cif")
