# Third-party
import astropy.coordinates as coord
from astropy.coordinates.matrix_utilities import matrix_product, rotation_matrix
from astropy.time import Time
import astropy.units as u
import numpy as np
from numpy import pi

# Project
from . import elements as elem
from .anomaly import (eccentric_anomaly_from_mean_anomaly,
                      true_anomaly_from_eccentric_anomaly)
from .utils import ArrayProcessor
from .barycenter import Barycenter
from .wrap import cy_rv_from_elements
from .reference_plane import ReferencePlaneFrame

__all__ = ['KeplerOrbit']


class KeplerOrbit:

    def __init__(self, elements=None, elements_type='kepler',
                 barycenter=None, **kwargs):
        """Represents a bound Kepler orbit.

        Parameters
        ----------
        elements : `twobody.OrbitalElements` subclass instance
            Either pass in an ``OrbitalElements`` object, e.g., an instance of
            `twobody.KeplerElements`, or pass in the element names themselves.
            If the latter, anything passed in as kwargs gets passed to the
            elements class specified by ``elements_type``. The element names
            for the default ``elements_type`` are included below for
            convenience.
        elements_type : str (optional)
            Ignore if you pass in an instantiated ``OrbitalElements`` object.
            This argument controls the class that the ``kwargs`` are passed to.
            The default is ``'kepler'``, meaning all keyword arguments get
            passed to the `twobody.KeplerElements` class.
        barycenter : `twobody.Barycenter` (optional)
            Parameters that control specification of the barycenter of the
            orbit.

        Kepler elements
        ---------------
        P : quantity_like [time]
            Orbital period.
        a : quantity_like [length] (optional)
            Semi-major axis. If unspecified, computed orbits will be unscaled.
        e : numeric (optional)
            Orbital eccentricity. Default is circular, ``e=0``.
        omega : quantity_like, `~astropy.coordinates.Angle` [angle]
            Argument of pericenter.
        i : quantity_like, `~astropy.coordinates.Angle` [angle]
            Inclination of the orbit.
        Omega : quantity_like, `~astropy.coordinates.Angle` [angle]
            Longitude of the ascending node.
        M0 : quantity_like, `~astropy.coordinates.Angle` [angle] (optional)
            Mean anomaly at epoch ``t0``. Default is 0º if not specified.
        t0 : numeric, `~astropy.coordinates.Time` (optional)
            Reference epoch. If a number is passed in, it is assumed to be
            a solar system barycentric modified julian date (BMJD). The default
            is J2000 if not specified.
        units : `~twobody.units.UnitSystem`, iterable (optional)
            The unit system to represent quantities in. The default unit system
            is accessible as `KeplerElements.default_units`.

        Examples
        --------
        As described above, you can either create an ``Elements`` object and
        then pass this to ``KeplerOrbit``, e.g.,

            >>> import astropy.units as u
            >>> from astropy.time import Time
            >>> from twobody import KeplerElements
            >>> t0 = Time(2459812.641, format='jd') # reference epoch
            >>> elem = KeplerElements(a=1.5*u.au, e=0.5, P=1.*u.year,
            ...                       omega=67*u.deg, i=21.*u.deg,
            ...                       Omega=33*u.deg, M0=53*u.deg, t0=t0)
            >>> orb = KeplerOrbit(elem)

        Or, you can pass in the element names as arguments to the
        ``KeplerOrbit`` class:

            >>> orb = KeplerOrbit(a=1.5*u.au, e=0.5, P=1.*u.year,
            ...                   omega=67*u.deg, i=21.*u.deg, Omega=33*u.deg,
            ...                   M0=53*u.deg, t0=t0)
        """

        if elements is None:
            elements_cls = getattr(elem,
                                   "{0}Elements"
                                   .format(elements_type.capitalize()))

            # pass everything in kwargs to the class initializer
            elements = elements_cls(**kwargs)

        elif not isinstance(elements, elem.OrbitalElements):
            raise TypeError("'elements' must be an instance of an "
                            "OrbitalElements subclass.")

        if barycenter is not None and not isinstance(barycenter, Barycenter):
            raise TypeError("barycenter must be a twobody.Barycenter instance")

        self.elements = elements
        self.barycenter = barycenter

    def __getattr__(self, name):

        # This gives access to the orbital element components directly from the
        # Orbit instance
        if hasattr(self.elements, name):
            return getattr(self.elements, name)

        else:
            raise AttributeError("type object '{0}' has no attribute '{1}'"
                                 .format(self.__class__.__name__, name))

    def unscaled_radial_velocity(self, time,
                                 anomaly_tol=None, anomaly_maxiter=None):
        """Compute the unscaled radial velocity of the body at the specified
        times relative to the barycenter or reference point, i.e. in the
        reference plane system not in a solar system barycentric frame.

        Parameters
        ----------
        time : array_like, `astropy.time.Time`
            Array of times as barycentric MJD values, or an Astropy
            `~astropy.time.Time` object containing the times to evaluate at.
        anomaly_tol : numeric (optional)
            Tolerance passed to
            `~twobody.eccentric_anomaly_from_mean_anomaly` for solving
            for the eccentric anomaly. See default value in that function.
        anomaly_maxiter : numeric (optional)
            Maximum number of iterations to use in
            `~twobody.eccentric_anomaly_from_mean_anomaly` for solving
            for the eccentric anomaly. See default value in that function.

        Returns
        -------
        rv : numeric [m/s]
            Relative radial velocity - does not include systemtic velocity!
        """
        if anomaly_tol is None:
            # TODO: make this a config item?
            anomaly_tol = 1E-10

        if anomaly_maxiter is None:
            # TODO: make this a config item?
            anomaly_maxiter = 128

        # TODO: do we always want to use MJD? precision issues...
        time = time.tcb.mjd
        proc = ArrayProcessor(time)
        t, = proc.prepare_arrays()
        rv = cy_rv_from_elements(t, self.P.to(u.day).value, 1., self.e,
                                 self.omega.to(u.radian).value,
                                 self.M0.to(u.radian).value,
                                 self.t0.tcb.mjd,
                                 anomaly_tol, anomaly_maxiter)
        return np.atleast_1d(proc.prepare_result(rv))

    def radial_velocity(self, time, anomaly_tol=None, anomaly_maxiter=None):
        """Compute the radial velocity of the body at the specified times
        relative to the barycenter or reference point, i.e. in the reference
        plane system not in a solar system barycentric frame.

        This should always be close (in a machine precision sense) to
        ``orbit.reference_plane(time).``

        When the barycenter is assumed to be at rest with respect to the
        observer, this should be equivalent to
        ``orbit.icrs(time).radial_velocity``

        Parameters
        ----------
        time : array_like, `astropy.time.Time`
            Array of times as barycentric MJD values, or an Astropy
            `~astropy.time.Time` object containing the times to evaluate at.
        anomaly_tol : numeric (optional)
            Tolerance passed to
            `~twobody.eccentric_anomaly_from_mean_anomaly` for solving
            for the eccentric anomaly. See default value in that function.
        anomaly_maxiter : numeric (optional)
            Maximum number of iterations to use in
            `~twobody.eccentric_anomaly_from_mean_anomaly` for solving
            for the eccentric anomaly. See default value in that function.
        """

        if self.barycenter is not None:
            rv0 = self.barycenter.origin.radial_velocity
        else:
            rv0 = 0 * u.km / u.s

        return self.K * self.unscaled_radial_velocity(time) + rv0

    def reference_plane(self, time):
        """Compute the orbit at specified times in the two-body barycentric
        frame aligned with the reference plane coordinate system (XYZ).

        Parameters
        ----------
        time : array_like, `astropy.time.Time`
            Array of times as barycentric MJD values, or an Astropy
            `~astropy.time.Time` object containing the times to evaluate at.
        """

        # mean anomaly
        with u.set_enabled_equivalencies(u.dimensionless_angles()):
            M = 2*pi * (time.tcb - self.t0.tcb) / self.P - self.M0
            M = M.to(u.radian)

        # eccentric anomaly
        E = eccentric_anomaly_from_mean_anomaly(M, self.e)

        # true anomaly
        f = true_anomaly_from_eccentric_anomaly(E, self.e)

        # distance from center of mass to orbiting body
        r = self.a * (1. - self.e * np.cos(E))

        # compute the orbit in the cartesian, orbital plane system (xyz):
        x = r * np.cos(f)
        y = r * np.sin(f)
        z = np.zeros_like(x)

        fac = 2*pi * self.a / self.P / np.sqrt(1 - self.e**2)
        vx = -fac * np.sin(f)
        vy = fac * (np.cos(f) + self.e)
        vz = np.zeros_like(vx)

        xyz = coord.CartesianRepresentation(x=x, y=y, z=z)
        vxyz = coord.CartesianDifferential(d_x=vx, d_y=vy, d_z=vz)

        # Construct rotation matrix to take the orbit from the orbital plane
        # system (xyz) to the reference plane system (XYZ):
        R1 = rotation_matrix(-self.omega, axis='z')
        R2 = rotation_matrix(self.i, axis='x')
        R3 = rotation_matrix(self.Omega, axis='z')
        Rot = matrix_product(R3, R2, R1)

        # Rotate to the reference plane system
        XYZ = coord.CartesianRepresentation(matrix_product(Rot, xyz.xyz))
        VXYZ = coord.CartesianDifferential(matrix_product(Rot, vxyz.d_xyz))
        XYZ = XYZ.with_differentials(VXYZ)

        kw = dict()
        if self.barycenter is not None:
            kw['origin'] = self.barycenter.origin
        return ReferencePlaneFrame(XYZ, **kw)

    def icrs(self, time):
        """
        TODO: docstring
        """
        rp = self.reference_plane(time)

        icrs_cart = rp.transform_to(coord.ICRS).cartesian
        icrs_pos = icrs_cart.without_differentials()
        icrs_vel = icrs_cart.differentials['s']

        bary_cart = self.barycenter.origin.cartesian
        bary_vel = bary_cart.differentials['s']

        dt = time - self.barycenter.t0
        dx = (bary_vel * dt).to_cartesian()

        new_pos = icrs_pos + dx
        new_vel = icrs_vel + bary_vel

        return coord.ICRS(new_pos.with_differentials(new_vel))

    def plot_rv(self, t, ax=None, rv_unit=None, t_kwargs=None,
                plot_kwargs=None):
        """Plot the line-of-sight or radial velocity at the specified times.

        Parameters
        ----------
        t : array_like, `~astropy.time.Time`
            Time array. Either in BMJD or as an Astropy time.
        ax : `~matplotlib.axes.Axes`, optional
            The axis to draw on (default is to grab the current
            axes using `~matplotlib.pyplot.gca`).
        rv_unit : `~astropy.units.UnitBase`, optional
            Units to plot the radial velocities in (default is km/s).
        t_kwargs : dict, optional
            Keyword arguments passed to :class:`astropy.time.Time` with the
            input time array. For example, ``dict(format='mjd', scale='tcb')``
            for Barycentric MJD.
        plot_kwargs : dict, optional
            Any additional arguments or style settings passed to
            :func:`matplotlib.pyplot.plot`.

        Returns
        -------
        ax : `~matplotlib.axes.Axes`
            The matplotlib axes object that the RV curve was drawn on.

        """

        if ax is None:
            import matplotlib.pyplot as plt
            ax = plt.gca()

        if rv_unit is None:
            rv_unit = u.km / u.s

        if t_kwargs is None:
            t_kwargs = dict(format='mjd', scale='tcb')

        if plot_kwargs is None:
            plot_kwargs = dict()

        style = plot_kwargs.copy()
        style.setdefault('linestyle', '-')
        style.setdefault('alpha', 0.5)
        style.setdefault('marker', None)

        if not isinstance(t, Time):
            t = Time(t, **t_kwargs)
        rv = self.radial_velocity(t).to(rv_unit).value

        _t = getattr(getattr(t, t_kwargs['scale']), t_kwargs['format'])
        ax.plot(_t, rv, **style)

        return ax
