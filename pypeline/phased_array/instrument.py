# #############################################################################
# instrument.py
# =============
# Author : Sepand KASHANI [sep@zurich.ibm.com]
# #############################################################################

"""
Instrument-related operations and geometry.
"""

import pathlib

import astropy.coordinates as coord
import astropy.time as time
import numpy as np
import pandas as pd
import pkg_resources as pkg
import plotly.graph_objs as go
import scipy.linalg as linalg

import pypeline.core as core
import pypeline.util.argcheck as chk
import pypeline.util.array as array
import pypeline.util.math.linalg as pylinalg
import pypeline.util.math.sphere as sph


def is_antenna_index(x):
    """
    Return :py:obj:`True` if `x` is a valid antenna index.

    A valid antenna index is a :py:class:`~pandas.MultiIndex` having columns

    * STATION_ID : int
    * ANTENNA_ID : int
    """
    if chk.is_instance(pd.MultiIndex)(x):
        col_names = ('STATION_ID', 'ANTENNA_ID')
        if tuple(x.names) == col_names:
            for col in col_names:
                ids = x.get_level_values(col).values
                if not chk.has_integers(ids):
                    return False
            return True

    return False


def _as_InstrumentGeometry(df):
    inst_geom = InstrumentGeometry(xyz=df.values,
                                   ant_idx=df.index)
    return inst_geom


class InstrumentGeometry(array.LabeledMatrix):
    """
    Position of antennas in a particular reference frame.

    Examples
    --------
    .. testsetup::

       import numpy as np
       import pandas as pd
       from pypeline.phased_array.instrument import InstrumentGeometry


    .. doctest::

       >>> geometry = InstrumentGeometry(xyz=np.arange(6 * 3).reshape(6, 3),
       ...                               ant_idx=pd.MultiIndex.from_product(
       ...                                   [range(3), range(2)],
       ...                                   names=['STATION_ID', 'ANTENNA_ID']))

       >>> geometry.data
       array([[ 0,  1,  2],
              [ 3,  4,  5],
              [ 6,  7,  8],
              [ 9, 10, 11],
              [12, 13, 14],
              [15, 16, 17]])

       >>> geometry.index[0]
       MultiIndex(levels=[[0, 1, 2], [0, 1]],
                  labels=[[0, 0, 1, 1, 2, 2], [0, 1, 0, 1, 0, 1]],
                  names=['STATION_ID', 'ANTENNA_ID'])
    """

    @chk.check(dict(xyz=chk.has_reals,
                    ant_idx=is_antenna_index))
    def __init__(self, xyz, ant_idx):
        """
        Parameters
        ----------
        xyz : :py:class:`~numpy.ndarray`
            (N_antenna, 3) Cartesian coordinates.
        ant_idx : :py:class:`~pandas.MultiIndex`
            (N_antenna,) index.
        """
        xyz = np.array(xyz, copy=False)
        N_antenna = len(xyz)
        if not chk.has_shape((N_antenna, 3))(xyz):
            raise ValueError('Parameter[xyz] must be a (N_antenna, 3) array.')

        N_idx = len(ant_idx)
        if N_idx != N_antenna:
            raise ValueError('Parameter[xyz] and Parameter[ant_idx] are not '
                             'compatible.')

        col_idx = pd.Index(['X', 'Y', 'Z'], name='COORDINATE')
        super().__init__(xyz, ant_idx, col_idx)

    def as_frame(self):
        """
        Returns
        -------
        :py:class:`~pandas.DataFrame`
            (N_antenna, 3) view of coordinates.
        """
        df = pd.DataFrame(data=self.data,
                          index=self.index[0],
                          columns=self.index[1].values)
        return df

    @chk.check('title', chk.is_instance(str))
    def draw(self, title=''):
        """
        Plot antenna coordinates in 3D.

        Parameters
        ----------
        title : str
            Title of the graph. (Default = '')

        Returns
        -------
        :py:class:`plotly.graph_objs.Figure`
            3D Figure.

        Examples
        --------
        .. doctest::

           import plotly.offline as py

           cfg = InstrumentGeometry(xyz=np.random.randn(6, 3),
                                    ant_idx=pd.MultiIndex.from_product(
                                        [range(3), range(2)],
                                        names=['STATION_ID', 'ANTENNA_ID']))

           fig = cfg.draw(title='Random Array')
           py.plot(fig)

        Notes
        -----
        For visualization purposes, the instrument's center of gravity is mapped to the origin.
        """
        # Cartesian Axes
        arm_length = np.std(self.data, axis=0).max()
        frame_trace = go.Scatter3d(hoverinfo='text+name',
                                   line={'width': 6},
                                   marker={'color': 'rgb(0,0.5,0)'},
                                   mode='lines+markers+text',
                                   name='Reference Frame',
                                   text=['X', 'O', 'Y', 'O', 'Z'],
                                   textfont={'color': 'black'},
                                   textposition='middle center',
                                   x=[arm_length, 0, 0, 0, 0],
                                   y=[0, 0, arm_length, 0, 0],
                                   z=[0, 0, 0, 0, arm_length])

        # Instrument Layout
        df = self.as_frame()
        df = df - df.mean()
        instrument_trace = []
        for station_id, station in df.groupby(level='STATION_ID'):
            X, Y, Z = station.values.T

            antenna_id = station.index.get_level_values('ANTENNA_ID')
            labels = [f'antenna {_}' for _ in antenna_id]

            station_trace = go.Scatter3d(hoverinfo='text+name',
                                         marker={'size': 2},
                                         mode='markers',
                                         name=f'station {station_id}',
                                         text=labels,
                                         x=X,
                                         y=Y,
                                         z=Z)
            instrument_trace += [station_trace]

        data = go.Data([frame_trace] + instrument_trace)
        layout = go.Layout(scene={'aspectmode': 'data',
                                  'camera': {'eye': {'x': 1.25,
                                                     'y': 1.25,
                                                     'z': 1.25}},
                                  'xaxis': {'title': 'X [m]'},
                                  'yaxis': {'title': 'Y [m]'},
                                  'zaxis': {'title': 'Z [m]'}},
                           title=title)

        fig = go.Figure(data=data, layout=layout)
        return fig


class InstrumentGeometryBlock(core.Block):
    """
    Compute antenna positions.
    """

    @chk.check(dict(inst_geom=chk.is_instance(InstrumentGeometry),
                    N_station=chk.allow_None(chk.is_integer)))
    def __init__(self, inst_geom, N_station=None):
        """
        Parameters
        ----------
        inst_geom : :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            Instrument geometry.
        N_station : int
            Number of stations to use. (Default = all)

            Sometimes only a subset of an instrument's stations are desired.
            Setting `N_station` limits the number of stations to those that appear first in `inst_geom` when sorted by STATION_ID.
        """
        super().__init__()
        if N_station is not None:
            if N_station < 1:
                raise ValueError('Parameter[N_station] must be positive.')

        self._layout = inst_geom.as_frame()

        if N_station is not None:
            stations = np.unique(inst_geom
                                 .index[0]
                                 .get_level_values('STATION_ID'))[:N_station]
            self._layout = self._layout.loc[stations]

    def __call__(self, *args, **kwargs):
        """
        Determine instrument antenna positions.

        Parameters
        ----------
        *args
            Positional arguments.
        **kwargs
            Keyword arguments.
        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            Instrument geometry.
        """
        raise NotImplementedError


class StationaryInstrumentGeometryBlock(InstrumentGeometryBlock):
    """
    Sub-class specialized in instruments that are stationary, i.e. that do not move with time.
    """

    @chk.check(dict(inst_geom=chk.is_instance(InstrumentGeometry),
                    N_station=chk.allow_None(chk.is_integer)))
    def __init__(self, inst_geom, N_station=None):
        """
        Parameters
        ----------
        inst_geom : :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            Instrument geometry.
        N_station : int
            Number of stations to use. (Default = all)

            Sometimes only a subset of an instrument's stations are desired.
            Setting `N_station` limits the number of stations to those that appear first in `inst_geom` when sorted by STATION_ID.
        """
        super().__init__(inst_geom, N_station)

    def __call__(self):
        """
        Determine instrument antenna positions.

        As the instrument's geometry does not change through time, :py:func:`~pypeline.phased_array.instrument.StationaryInstrumentGeometryBlock.__call__` always returns the same object.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            Instrument geometry.
        """
        return _as_InstrumentGeometry(self._layout)


class PyramicBlock(StationaryInstrumentGeometryBlock):
    """
    Pyramic 48-element 3D microphone array.
    """

    def __init__(self):
        """

        """
        inst_geom = self._get_geometry()
        super().__init__(inst_geom)

    def _get_geometry(self):
        """
        Generate instrument geometry.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
        """
        x = 0.27 + 2 * 0.015  # length of one side
        c1, c2, c3, c4 = 1 / np.sqrt(3), np.sqrt(2 / 3), np.sqrt(3) / 6, 0.5
        corners = np.array([[0, x * c1, -x * c3, -x * c3],
                            [0, 0, x * c4, -x * c4],
                            [0, x * c2, x * c2, x * c2]])

        # Relative placement of microphones on one PCB.
        pcb = np.r_[-0.100, -0.060, -0.020, -0.004, 0.004, 0.020, 0.060, 0.100]

        def line(p1, p2, dist):
            center = (p1 + p2) / 2.
            unit_vec = (p2 - p1) / linalg.norm(p2 - p1)

            pts = [center + d * unit_vec for d in dist]
            return pts

        coordinates = np.array(line(corners[:, 0], corners[:, 3], pcb) +
                               line(corners[:, 3], corners[:, 2], pcb) +
                               line(corners[:, 0], corners[:, 1], pcb) +
                               line(corners[:, 1], corners[:, 3], pcb) +
                               line(corners[:, 0], corners[:, 2], pcb) +
                               line(corners[:, 2], corners[:, 1], pcb))

        # Reference point is 1cm below zero-th microphone
        coordinates[:, 2] += 0.01 - coordinates[0, 2]

        N_mic = len(coordinates)
        idx = pd.MultiIndex.from_product([range(N_mic), range(1)],
                                         names=['STATION_ID', 'ANTENNA_ID'])
        inst_geom = InstrumentGeometry(coordinates, idx)
        return inst_geom


class CompactSixBlock(StationaryInstrumentGeometryBlock):
    """
    Compact-Six 6-element ring microphone array.
    """

    def __init__(self):
        """

        """
        inst_geom = self._get_geometry()
        super().__init__(inst_geom)

    def _get_geometry(self):
        """
        Generate instrument geometry.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
        """
        N_mic = 6
        radius = 0.0675

        angle = np.linspace(0, 2 * np.pi, num=N_mic, endpoint=False)
        coordinates = radius * np.stack((np.cos(angle),
                                         np.sin(angle),
                                         np.zeros(N_mic)), axis=1)

        idx = pd.MultiIndex.from_product([range(N_mic), range(1)],
                                         names=['STATION_ID', 'ANTENNA_ID'])
        inst_geom = InstrumentGeometry(coordinates, idx)
        return inst_geom


class EarthBoundInstrumentGeometryBlock(InstrumentGeometryBlock):
    """
    Sub-class specialized in instruments that move with the Earth, such as radio telescopes.
    """

    @chk.check(dict(inst_geom=chk.is_instance(InstrumentGeometry),
                    N_station=chk.allow_None(chk.is_integer)))
    def __init__(self, inst_geom, N_station=None):
        """
        Parameters
        ----------
        inst_geom : :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            ITRS instrument geometry.
        N_station : int
            Number of stations to use. (Default = all)

            Sometimes only a subset of an instrument’s stations are desired.
            Setting `N_station` limits the number of stations to those that appear first in `inst_geom` when sorted by STATION_ID.
        """
        super().__init__(inst_geom, N_station)

    @chk.check('time', chk.is_instance(time.Time))
    def __call__(self, time):
        """
        Determine instrument antenna positions in ICRS.

        Parameters
        ----------
        time : :py:class:`~astropy.time.Time`
            Moment at which the coordinates are wanted.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            ICRS instrument geometry.
        """
        layout = self._layout.loc[:, ['X', 'Y', 'Z']].values.T
        r = linalg.norm(layout, axis=0)

        itrs_layout = coord.CartesianRepresentation(layout)
        itrs_position = coord.SkyCoord(itrs_layout, obstime=time, frame='itrs')
        icrs_position = r * (itrs_position
                             .transform_to('icrs')
                             .cartesian
                             .xyz)
        icrs_layout = pd.DataFrame(data=icrs_position.T,
                                   index=self._layout.index,
                                   columns=('X', 'Y', 'Z'))
        return _as_InstrumentGeometry(icrs_layout)


class LofarBlock(EarthBoundInstrumentGeometryBlock):
    """
    `LOw-Frequency ARray (LOFAR) <http://www.lofar.org/>`_ located in Europe.

    This LOFAR model consists of 62 stations, each containing between 17 to 24 HBA dipole antennas.
    """

    @chk.check('N_station', chk.allow_None(chk.is_integer))
    def __init__(self, N_station=None):
        """
        Parameters
        ----------
        N_station : int
            Number of stations to use. (Default = all)

            Sometimes only a subset of an instrument’s stations are desired.
            Setting `N_station` limits the number of stations to those that appear first in `inst_geom` when sorted by STATION_ID.
        """
        inst_geom = self._get_geometry()
        super().__init__(inst_geom, N_station)

    def _get_geometry(self):
        """
        Load instrument geometry.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            ITRS instrument geometry.
        """
        rel_path = pathlib.Path('data', 'phased_array',
                                'instrument', 'LOFAR.csv')
        abs_path = pkg.resource_filename('pypeline', str(rel_path))

        itrs_geom = (pd.read_csv(abs_path)
                     .set_index(['STATION_ID', 'ANTENNA_ID']))

        inst_geom = _as_InstrumentGeometry(itrs_geom)
        return inst_geom


class MwaBlock(EarthBoundInstrumentGeometryBlock):
    """
    `Murchison Widefield Array (MWA) <http://www.mwatelescope.org/>`_ located in Australia.

    MWA consists of 128 stations, each containing 16 dipole antennas.
    """

    @chk.check(dict(N_station=chk.allow_None(chk.is_integer),
                    station_only=chk.is_boolean))
    def __init__(self, N_station=None, station_only=False):
        """
        Parameters
        ----------
        N_station : int
            Number of stations to use. (Default = all)

            Sometimes only a subset of an instrument’s stations are desired.
            Setting `N_station` limits the number of stations to those that appear first in `inst_geom` when sorted by STATION_ID.

        station_only : bool
            If :py:obj:`True`, model MWA stations as single-element antennas. (Default = False)
        """
        inst_geom = self._get_geometry(station_only)
        super().__init__(inst_geom, N_station)

    def _get_geometry(self, station_only):
        """
        Load instrument geometry.

        Parameters
        ----------
        station_only : bool
            If :py:obj:`True`, model stations as single-element antennas.

        Returns
        -------
        :py:class:`~pypeline.phased_array.instrument.InstrumentGeometry`
            ITRS instrument geometry.
        """
        rel_path = pathlib.Path('data', 'phased_array',
                                'instrument', 'MWA.csv')
        abs_path = pkg.resource_filename('pypeline', str(rel_path))

        itrs_geom = (pd.read_csv(abs_path)
                     .set_index('STATION_ID'))

        station_id = itrs_geom.index.get_level_values('STATION_ID')
        if station_only:
            itrs_geom.index = (pd.MultiIndex
                .from_product(
                [station_id, [0]],
                names=['STATION_ID', 'ANTENNA_ID']))
        else:
            # Generate flat 4x4 antenna grid pointing towards the Noth pole.
            x_lim = y_lim = 1.65
            lY, lX = np.meshgrid(np.linspace(-y_lim, y_lim, 4),
                                 np.linspace(-x_lim, x_lim, 4),
                                 indexing='ij')
            l = np.stack((lX, lY, np.zeros((4, 4))), axis=0)

            # For each station: rotate 4x4 array to lie on the sphere's surface.
            xyz_station = itrs_geom.loc[:, ['X', 'Y', 'Z']].values
            df_stations = []
            for st_id, st_cog in zip(station_id, xyz_station):
                _, st_colat, st_lon = sph.cart2pol(*st_cog)
                st_cog_unit = sph.pol2cart(1, st_colat, st_lon).reshape(-1)

                R_1 = pylinalg.rot([0, 0, 1], st_lon)
                R_2 = pylinalg.rot(axis=np.cross([0, 0, 1], st_cog_unit),
                                   angle=st_colat)
                R = R_2 @ R_1

                st_layout = np.reshape(st_cog.reshape(3, 1, 1) +
                                       np.tensordot(R, l, axes=1), (3, -1))
                idx = (pd.MultiIndex
                       .from_product([[st_id], range(16)],
                                     names=['STATION_ID', 'ANTENNA_ID']))
                df_stations += [pd.DataFrame(data=st_layout.T,
                                             index=idx,
                                             columns=['X', 'Y', 'Z'])]
            itrs_geom = pd.concat(df_stations)

        inst_geom = _as_InstrumentGeometry(itrs_geom)
        return inst_geom