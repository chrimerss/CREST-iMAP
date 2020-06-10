""" ANUGA models the effect of tsunamis and flooding upon a terrain mesh.
    In typical usage, a Domain class is created for a particular piece of
    terrain. Boundary conditions are specified for the domain, such as inflow
    and outflow, and then the simulation is run.

    This is the public API to ANUGA. It provides a toolkit of often-used
    modules, which can be used directly by including the following line in
    the user's code:

    import anuga

    This usage pattern abstracts away the internal heirarchy of the ANUGA
    system, allowing the user to concentrate on writing simulations without
    searching through the ANUGA source tree for the functions that they need.

    Also, it isolates the user from "under-the-hood" refactorings.
"""

# -----------------------------------------------------
# Make selected classes available directly
# -----------------------------------------------------


__version__ = '2.0.3'

__svn_revision__ = filter(str.isdigit, "$Revision: 9737 $")

__svn_revision_date__ = "$Date: 2016-10-04 16:13:00 +1100 (Tue, 04 Oct 2016) $"[7:-1]


# We first need to detect if we're being called as part of the anuga setup
# procedure itself in a reliable manner.
try:
    __ANUGA_SETUP__
except NameError:
    __ANUGA_SETUP__ = False


if __ANUGA_SETUP__:
    import sys as _sys
    _sys.stderr.write('Running from anuga source directory.\n')
    del _sys
else:

    try:
        from cresthh.anuga.__config__ import show as show_config
    except ImportError:
        msg = """Error importing anuga: you should not try to import anuga from
        its source directory; please exit the anuga source tree, and relaunch
        your python interpreter from there."""
        raise ImportError(msg)

    # ---------------------------------
    # NetCDF changes stdout to terminal\
    # Causes trouble when using jupyter
    # ---------------------------------
    import sys
    _stdout = sys.stdout

    # ---------------------------------
    # Setup the nose tester from numpy
    # ---------------------------------
    from numpy.testing import Tester
    test = Tester().test

    # --------------------------------
    # Important basic classes
    # --------------------------------
    
    from cresthh.anuga.shallow_water.shallow_water_domain import Domain
    from cresthh.anuga.abstract_2d_finite_volumes.quantity import Quantity
    from cresthh.anuga.abstract_2d_finite_volumes.region import Region
    from cresthh.anuga.geospatial_data.geospatial_data import Geospatial_data
    from cresthh.anuga.coordinate_transforms.geo_reference import Geo_reference
    from cresthh.anuga.operators.base_operator import Operator
    from cresthh.anuga.structures.structure_operator import Structure_operator

    from cresthh.anuga.utilities.animate import SWW_plotter
    from cresthh.anuga.utilities.animate import Domain_plotter


    from cresthh.anuga.abstract_2d_finite_volumes.generic_domain import Generic_Domain
    from cresthh.anuga.abstract_2d_finite_volumes.neighbour_mesh import Mesh

    # ------------------------------------------------------------------------------
    # Miscellaneous
    # ------------------------------------------------------------------------------
    from cresthh.anuga.abstract_2d_finite_volumes.util import file_function, \
                                            sww2timeseries, sww2csv_gauges, \
                                            csv2timeseries_graphs

    from cresthh.anuga.abstract_2d_finite_volumes.mesh_factory import rectangular_cross, \
                                                        rectangular

    from cresthh.anuga.file.csv_file import load_csv_as_building_polygons,  \
                                    load_csv_as_polygons

    from cresthh.anuga.file.sts import create_sts_boundary

    from cresthh.anuga.file.ungenerate import load_ungenerate

    from cresthh.anuga.geometry.polygon import read_polygon
    from cresthh.anuga.geometry.polygon import plot_polygons
    from cresthh.anuga.geometry.polygon import inside_polygon
    from cresthh.anuga.geometry.polygon import polygon_area
    from cresthh.anuga.geometry.polygon_function import Polygon_function

    from cresthh.anuga.coordinate_transforms.lat_long_UTM_conversion import LLtoUTM, UTMtoLL

    from cresthh.anuga.abstract_2d_finite_volumes.pmesh2domain import \
                                                pmesh_to_domain_instance

    from cresthh.anuga.fit_interpolate.fit import fit_to_mesh_file
    from cresthh.anuga.fit_interpolate.fit import fit_to_mesh

    from cresthh.anuga.utilities.system_tools import file_length
    from cresthh.anuga.utilities.sww_merge import sww_merge_parallel as sww_merge
    from cresthh.anuga.utilities.file_utils import copy_code_files
    from cresthh.anuga.utilities.numerical_tools import safe_acos as acos
    from cresthh.anuga.utilities import plot_utils


    from cresthh.anuga.caching import cache
    from os.path import join
    from cresthh.anuga.config import indent

    from cresthh.anuga.utilities.parse_time import parse_time

    # ----------------------------
    # Parallel api
    # ----------------------------
    ## from anuga_parallel.parallel_api import distribute
    ## from anuga_parallel.parallel_api import myid, numprocs, get_processor_name
    ## from anuga_parallel.parallel_api import send, receive
    ## from anuga_parallel.parallel_api import pypar_available, barrier, finalize

    ## if pypar_available:
    ##     from anuga_parallel.parallel_api import sequential_distribute_dump
    ##     from anuga_parallel.parallel_api import sequential_distribute_load

    from cresthh.anuga.parallel.parallel_api import distribute
    from cresthh.anuga.parallel.parallel_api import myid, numprocs, get_processor_name
    from cresthh.anuga.parallel.parallel_api import send, receive
    from cresthh.anuga.parallel.parallel_api import pypar_available, barrier, finalize
    from cresthh.anuga.parallel.parallel_api import collect_value

    if pypar_available:
        from cresthh.anuga.parallel.parallel_api import sequential_distribute_dump
        from cresthh.anuga.parallel.parallel_api import sequential_distribute_load

    # -----------------------------
    # Checkpointing
    # -----------------------------
    from cresthh.anuga.shallow_water.checkpoint import load_checkpoint_file

    # -----------------------------
    # SwW Standard Boundaries
    # -----------------------------
    from cresthh.anuga.shallow_water.boundaries import File_boundary
    from cresthh.anuga.shallow_water.boundaries import Reflective_boundary
    from cresthh.anuga.shallow_water.boundaries import Field_boundary
    from cresthh.anuga.shallow_water.boundaries import \
                        Time_stage_zero_momentum_boundary
    from cresthh.anuga.shallow_water.boundaries import \
                        Transmissive_stage_zero_momentum_boundary
    from cresthh.anuga.shallow_water.boundaries import \
                        Transmissive_momentum_set_stage_boundary
    from cresthh.anuga.shallow_water.boundaries import \
                        Transmissive_n_momentum_zero_t_momentum_set_stage_boundary
    from cresthh.anuga.shallow_water.boundaries import \
                        Flather_external_stage_zero_velocity_boundary
    from cresthh.anuga.abstract_2d_finite_volumes.generic_boundary_conditions import \
                        Compute_fluxes_boundary

    # -----------------------------
    # General Boundaries
    # -----------------------------
    from cresthh.anuga.abstract_2d_finite_volumes.generic_boundary_conditions \
                                import Dirichlet_boundary
    from cresthh.anuga.abstract_2d_finite_volumes.generic_boundary_conditions \
                                import Time_boundary
    from cresthh.anuga.abstract_2d_finite_volumes.generic_boundary_conditions \
                                import Time_space_boundary
    from cresthh.anuga.abstract_2d_finite_volumes.generic_boundary_conditions \
                                import Transmissive_boundary

    # -----------------------------
    # Shallow Water Tsunamis
    # -----------------------------
    from cresthh.anuga.tsunami_source.smf import slide_tsunami, slump_tsunami

    # -----------------------------
    # Forcing
    # These are old, should use operators
    # -----------------------------
    from cresthh.anuga.shallow_water.forcing import Inflow, Rainfall, Wind_stress

    # -----------------------------
    # File conversion utilities
    # -----------------------------
    from cresthh.anuga.file_conversion.file_conversion import sww2obj
    from cresthh.anuga.file_conversion.file_conversion import timefile2netcdf
    from cresthh.anuga.file_conversion.file_conversion import tsh2sww
    from cresthh.anuga.file_conversion.urs2nc import urs2nc
    from cresthh.anuga.file_conversion.urs2sww import urs2sww
    from cresthh.anuga.file_conversion.urs2sts import urs2sts
    from cresthh.anuga.file_conversion.dem2pts import dem2pts
    from cresthh.anuga.file_conversion.esri2sww import esri2sww
    from cresthh.anuga.file_conversion.sww2dem import sww2dem, sww2dem_batch
    from cresthh.anuga.file_conversion.asc2dem import asc2dem
    from cresthh.anuga.file_conversion.xya2pts import xya2pts
    from cresthh.anuga.file_conversion.ferret2sww import ferret2sww
    from cresthh.anuga.file_conversion.dem2dem import dem2dem
    from cresthh.anuga.file_conversion.sww2array import sww2array

    # -----------------------------
    # Parsing arguments
    # -----------------------------
    from cresthh.anuga.utilities.argparsing import create_standard_parser
    from cresthh.anuga.utilities.argparsing import parse_standard_args


    def get_args():
        """ Explicitly parse the argument list using standard anuga arguments

        Don't use this if you want to setup your own parser
        """
        parser = create_standard_parser()
        return parser.parse_args()

    # -----------------------------
    # Running Script
    # -----------------------------
    from cresthh.anuga.utilities.run_anuga_script import run_script as run_anuga_script

    # ---------------------------
    # Simulation and Excel mesh_interface
    # ---------------------------
    from cresthh.anuga.simulation.simulation import Simulation

    # -----------------------------
    # Mesh API
    # -----------------------------
    from cresthh.anuga.pmesh.mesh_interface import create_mesh_from_regions

    # -----------------------------
    # SWW file access
    # -----------------------------
    from cresthh.anuga.shallow_water.sww_interrogate import get_flow_through_cross_section

    # ---------------------------
    # Operators
    # ---------------------------
    from cresthh.anuga.operators.kinematic_viscosity_operator import Kinematic_viscosity_operator

    from cresthh.anuga.operators.rate_operators import Rate_operator
    from cresthh.anuga.operators.set_friction_operators import Depth_friction_operator

    from cresthh.anuga.operators.set_elevation_operator import Set_elevation_operator
    from cresthh.anuga.operators.set_quantity_operator import Set_quantity_operator
    from cresthh.anuga.operators.set_stage_operator import Set_stage_operator


    from cresthh.anuga.operators.set_elevation import Set_elevation
    from cresthh.anuga.operators.set_quantity import Set_quantity
    from cresthh.anuga.operators.set_stage import Set_stage

    from cresthh.anuga.operators.sanddune_erosion_operator import Sanddune_erosion_operator
    from cresthh.anuga.operators.erosion_operators import Bed_shear_erosion_operator
    from cresthh.anuga.operators.erosion_operators import Flat_slice_erosion_operator
    from cresthh.anuga.operators.erosion_operators import Flat_fill_slice_erosion_operator

    # ---------------------------
    # Structure Operators
    # ---------------------------

    if pypar_available:
        from cresthh.anuga.parallel.parallel_operator_factory import Inlet_operator
        from cresthh.anuga.parallel.parallel_operator_factory import Boyd_box_operator
        from cresthh.anuga.parallel.parallel_operator_factory import Boyd_pipe_operator
        from cresthh.anuga.parallel.parallel_operator_factory import Weir_orifice_trapezoid_operator
        from cresthh.anuga.parallel.parallel_operator_factory import Internal_boundary_operator
    else:
        from cresthh.anuga.structures.inlet_operator import Inlet_operator
        from cresthh.anuga.structures.boyd_box_operator import Boyd_box_operator
        from cresthh.anuga.structures.boyd_pipe_operator import Boyd_pipe_operator
        from cresthh.anuga.structures.weir_orifice_trapezoid_operator import Weir_orifice_trapezoid_operator
        from cresthh.anuga.structures.internal_boundary_operator import Internal_boundary_operator

    from cresthh.anuga.structures.internal_boundary_functions import pumping_station_function

    # ----------------------------
    # Parallel distribute
    # ----------------------------

    # ----------------------------
    #
    # Added by Petar Milevski 10/09/2013

    from cresthh.anuga.utilities.model_tools import get_polygon_from_single_file
    from cresthh.anuga.utilities.model_tools import get_polygons_from_Mid_Mif
    from cresthh.anuga.utilities.model_tools import get_polygon_list_from_files
    from cresthh.anuga.utilities.model_tools import get_polygon_dictionary
    from cresthh.anuga.utilities.model_tools import get_polygon_value_list
    from cresthh.anuga.utilities.model_tools import read_polygon_dir
    from cresthh.anuga.utilities.model_tools import read_hole_dir_multi_files_with_single_poly
    from cresthh.anuga.utilities.model_tools import read_multi_poly_file
    from cresthh.anuga.utilities.model_tools import read_hole_dir_single_file_with_multi_poly
    from cresthh.anuga.utilities.model_tools import read_multi_poly_file_value
    from cresthh.anuga.utilities.model_tools import Create_culvert_bridge_Operator
    from cresthh.anuga.utilities.model_tools import get_WCC_2002_Blockage_factor
    from cresthh.anuga.utilities.model_tools import get_WCC_2016_Blockage_factor

    # ---------------------------
    # User Access Functions
    # ---------------------------

    from cresthh.anuga.utilities.system_tools import get_user_name
    from cresthh.anuga.utilities.system_tools import get_host_name
    from cresthh.anuga.utilities.system_tools import get_version
    from cresthh.anuga.utilities.system_tools import get_revision_number
    from cresthh.anuga.utilities.system_tools import get_revision_date
    from cresthh.anuga.utilities.mem_time_equation import estimate_time_mem

    # -------------------------
    # create domain functions
    # -------------------------
    from cresthh.anuga.extras import create_domain_from_regions
    from cresthh.anuga.extras import create_domain_from_file
    from cresthh.anuga.extras import rectangular_cross_domain


    #import logging as log
    from cresthh.anuga.utilities import log as log

    from cresthh.anuga.config import g
    from cresthh.anuga.config import velocity_protection

    # --------------------------------------
    # NetCDF changes stdout to the terminal
    # This resets it
    # --------------------------------------
    reload(sys)
    sys.stdout = _stdout
