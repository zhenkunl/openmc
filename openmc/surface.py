from abc import ABCMeta
from collections import Iterable
from numbers import Real, Integral
from xml.etree import ElementTree as ET
from math import sqrt

from six import add_metaclass, string_types
import numpy as np

from openmc.checkvalue import check_type, check_value, check_greater_than
from openmc.region import Region, Intersection, Union


# A static variable for auto-generated Surface IDs
AUTO_SURFACE_ID = 10000

_BOUNDARY_TYPES = ['transmission', 'vacuum', 'reflective', 'periodic']


def reset_auto_surface_id():
    """Reset counters for all auto-generated surface IDs"""
    global AUTO_SURFACE_ID
    AUTO_SURFACE_ID = 10000


class Surface(object):
    """An implicit surface with an associated boundary condition.

    An implicit surface is defined as the set of zeros of a function of the
    three Cartesian coordinates. Surfaces in OpenMC are limited to a set of
    algebraic surfaces, i.e., surfaces that are polynomial in x, y, and z.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface. Note that periodic boundary conditions
        can only be applied to x-, y-, and z-planes, and only axis-aligned
        periodicity is supported.
    name : str, optional
        Name of the surface. If not specified, the name will be the empty
        string.

    Attributes
    ----------
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission', name=''):
        self.id = surface_id
        self.name = name
        self._type = ''
        self.boundary_type = boundary_type

        # A dictionary of the quadratic surface coefficients
        # Key        - coefficeint name
        # Value    - coefficient value
        self._coefficients = {}

        # An ordered list of the coefficient names to export to XML in the
        # proper order
        self._coeff_keys = []

    def __neg__(self):
        return Halfspace(self, '-')

    def __pos__(self):
        return Halfspace(self, '+')

    def __repr__(self):
        string = 'Surface\n'
        string += '{0: <16}{1}{2}\n'.format('\tID', '=\t', self._id)
        string += '{0: <16}{1}{2}\n'.format('\tName', '=\t', self._name)
        string += '{0: <16}{1}{2}\n'.format('\tType', '=\t', self._type)
        string += '{0: <16}{1}{2}\n'.format('\tBoundary', '=\t', self._boundary_type)

        coefficients = '{0: <16}'.format('\tCoefficients') + '\n'

        for coeff in self._coefficients:
            coefficients += '{0: <16}{1}{2}\n'.format(
                coeff, '=\t', self._coefficients[coeff])

        string += coefficients

        return string

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def type(self):
        return self._type

    @property
    def boundary_type(self):
        return self._boundary_type

    @property
    def coefficients(self):
        return self._coefficients

    @id.setter
    def id(self, surface_id):
        if surface_id is None:
            global AUTO_SURFACE_ID
            self._id = AUTO_SURFACE_ID
            AUTO_SURFACE_ID += 1
        else:
            check_type('surface ID', surface_id, Integral)
            check_greater_than('surface ID', surface_id, 0, equality=True)
            self._id = surface_id

    @name.setter
    def name(self, name):
        if name is not None:
            check_type('surface name', name, string_types)
            self._name = name
        else:
            self._name = ''

    @boundary_type.setter
    def boundary_type(self, boundary_type):
        check_type('boundary type', boundary_type, string_types)
        check_value('boundary type', boundary_type, _BOUNDARY_TYPES)
        self._boundary_type = boundary_type

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. If the half-space is
        unbounded in a particular direction, numpy.inf is used to represent
        infinity.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        return (np.array([-np.inf, -np.inf, -np.inf]),
                np.array([np.inf, np.inf, np.inf]))

    def to_xml_element(self):
        """Return XML representation of the surface

        Returns
        -------
        element : xml.etree.ElementTree.Element
            XML element containing source data

        """
        element = ET.Element("surface")
        element.set("id", str(self._id))

        if len(self._name) > 0:
            element.set("name", str(self._name))

        element.set("type", self._type)
        if self.boundary_type != 'transmission':
            element.set("boundary", self.boundary_type)
        element.set("coeffs", ' '.join([str(self._coefficients.setdefault(key, 0.0))
                                        for key in self._coeff_keys]))

        return element

    @staticmethod
    def from_hdf5(group):
        """Create surface from HDF5 group

        Parameters
        ----------
        group : h5py.Group
            Group in HDF5 file

        Returns
        -------
        openmc.Surface
            Instance of surface subclass

        """
        surface_id = int(group.name.split('/')[-1].lstrip('surface '))
        name = group['name'].value.decode() if 'name' in group else ''
        surf_type = group['type'].value.decode()
        bc = group['boundary_type'].value.decode()
        coeffs = group['coefficients'][...]

        # Create the Surface based on its type
        if surf_type == 'x-plane':
            x0 = coeffs[0]
            surface = XPlane(surface_id, bc, x0, name)

        elif surf_type == 'y-plane':
            y0 = coeffs[0]
            surface = YPlane(surface_id, bc, y0, name)

        elif surf_type == 'z-plane':
            z0 = coeffs[0]
            surface = ZPlane(surface_id, bc, z0, name)

        elif surf_type == 'plane':
            A, B, C, D = coeffs
            surface = Plane(surface_id, bc, A, B, C, D, name)

        elif surf_type == 'x-cylinder':
            y0, z0, R = coeffs
            surface = XCylinder(surface_id, bc, y0, z0, R, name)

        elif surf_type == 'y-cylinder':
            x0, z0, R = coeffs
            surface = YCylinder(surface_id, bc, x0, z0, R, name)

        elif surf_type == 'z-cylinder':
            x0, y0, R = coeffs
            surface = ZCylinder(surface_id, bc, x0, y0, R, name)

        elif surf_type == 'sphere':
            x0, y0, z0, R = coeffs
            surface = Sphere(surface_id, bc, x0, y0, z0, R, name)

        elif surf_type in ['x-cone', 'y-cone', 'z-cone']:
            x0, y0, z0, R2 = coeffs
            if surf_type == 'x-cone':
                surface = XCone(surface_id, bc, x0, y0, z0, R2, name)
            elif surf_type == 'y-cone':
                surface = YCone(surface_id, bc, x0, y0, z0, R2, name)
            elif surf_type == 'z-cone':
                surface = ZCone(surface_id, bc, x0, y0, z0, R2, name)

        elif surf_type == 'quadric':
            a, b, c, d, e, f, g, h, j, k = coeffs
            surface = Quadric(surface_id, bc, a, b, c, d, e, f, g,
                              h, j, k, name)

        return surface


class Plane(Surface):
    """An arbitrary plane of the form :math:`Ax + By + Cz = D`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    A : float, optional
        The 'A' parameter for the plane. Defaults to 1.
    B : float, optional
        The 'B' parameter for the plane. Defaults to 0.
    C : float, optional
        The 'C' parameter for the plane. Defaults to 0.
    D : float, optional
        The 'D' parameter for the plane. Defaults to 0.
    name : str, optional
        Name of the plane. If not specified, the name will be the empty string.

    Attributes
    ----------
    a : float
        The 'A' parameter for the plane
    b : float
        The 'B' parameter for the plane
    c : float
        The 'C' parameter for the plane
    d : float
        The 'D' parameter for the plane
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    periodic_surface : openmc.Surface
        If a periodic boundary condition is used, the surface with which this
        one is periodic with
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 A=1., B=0., C=0., D=0., name=''):
        super(Plane, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'plane'
        self._coeff_keys = ['A', 'B', 'C', 'D']
        self._periodic_surface = None
        self.a = A
        self.b = B
        self.c = C
        self.d = D

    @property
    def a(self):
        return self.coefficients['A']

    @property
    def b(self):
        return self.coefficients['B']

    @property
    def c(self):
        return self.coefficients['C']

    @property
    def d(self):
        return self.coefficients['D']

    @property
    def periodic_surface(self):
        return self._periodic_surface

    @a.setter
    def a(self, A):
        check_type('A coefficient', A, Real)
        self._coefficients['A'] = A

    @b.setter
    def b(self, B):
        check_type('B coefficient', B, Real)
        self._coefficients['B'] = B

    @c.setter
    def c(self, C):
        check_type('C coefficient', C, Real)
        self._coefficients['C'] = C

    @d.setter
    def d(self, D):
        check_type('D coefficient', D, Real)
        self._coefficients['D'] = D

    @periodic_surface.setter
    def periodic_surface(self, periodic_surface):
        check_type('periodic surface', periodic_surface, Plane)
        self._periodic_surface = periodic_surface
        periodic_surface._periodic_surface = self

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`Ax' + By' + Cz' - d`

        """

        x, y, z = point
        return self.a*x + self.b*y + self.c*z - self.d

    def to_xml_element(self):
        """Return XML representation of the surface

        Returns
        -------
        element : xml.etree.ElementTree.Element
            XML element containing source data

        """
        element = super(Plane, self).to_xml_element()

        # Add periodic surface pair information
        if self.boundary_type == 'periodic':
            if self.periodic_surface is not None:
                element.set("periodic_surface_id", str(self.periodic_surface.id))
        return element


class XPlane(Plane):
    """A plane perpendicular to the x axis of the form :math:`x - x_0 = 0`

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface. Only axis-aligned periodicity is
        supported, i.e., x-planes can only be paired with x-planes.
    x0 : float, optional
        Location of the plane. Defaults to 0.
    name : str, optional
        Name of the plane. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        Location of the plane
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    periodic_surface : openmc.Surface
        If a periodic boundary condition is used, the surface with which this
        one is periodic with
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., name=''):
        super(XPlane, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'x-plane'
        self._coeff_keys = ['x0']
        self.x0 = x0

    @property
    def x0(self):
        return self.coefficients['x0']

    @x0.setter
    def x0(self, x0):
        check_type('x0 coefficient', x0, Real)
        self._coefficients['x0'] = x0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the x-plane surface, the
        half-spaces are unbounded in their y- and z- directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([self.x0, np.inf, np.inf]))
        elif side == '+':
            return (np.array([self.x0, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`x' - x_0`

        """
        return point[0] - self.x0


class YPlane(Plane):
    """A plane perpendicular to the y axis of the form :math:`y - y_0 = 0`

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface. Only axis-aligned periodicity is
        supported, i.e., x-planes can only be paired with x-planes.
    y0 : float, optional
        Location of the plane
    name : str, optional
        Name of the plane. If not specified, the name will be the empty string.

    Attributes
    ----------
    y0 : float
        Location of the plane
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    periodic_surface : openmc.Surface
        If a periodic boundary condition is used, the surface with which this
        one is periodic with
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 y0=0., name=''):
        # Initialize YPlane class attributes
        super(YPlane, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'y-plane'
        self._coeff_keys = ['y0']
        self.y0 = y0

    @property
    def y0(self):
        return self.coefficients['y0']

    @y0.setter
    def y0(self, y0):
        check_type('y0 coefficient', y0, Real)
        self._coefficients['y0'] = y0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the y-plane surface, the
        half-spaces are unbounded in their x- and z- directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, self.y0, np.inf]))
        elif side == '+':
            return (np.array([-np.inf, self.y0, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`y' - y_0`

        """
        return point[1] - self.y0


class ZPlane(Plane):
    """A plane perpendicular to the z axis of the form :math:`z - z_0 = 0`

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface. Only axis-aligned periodicity is
        supported, i.e., x-planes can only be paired with x-planes.
    z0 : float, optional
        Location of the plane. Defaults to 0.
    name : str, optional
        Name of the plane. If not specified, the name will be the empty string.

    Attributes
    ----------
    z0 : float
        Location of the plane
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    periodic_surface : openmc.Surface
        If a periodic boundary condition is used, the surface with which this
        one is periodic with
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 z0=0., name=''):
        # Initialize ZPlane class attributes
        super(ZPlane, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'z-plane'
        self._coeff_keys = ['z0']
        self.z0 = z0

    @property
    def z0(self):
        return self.coefficients['z0']

    @z0.setter
    def z0(self, z0):
        check_type('z0 coefficient', z0, Real)
        self._coefficients['z0'] = z0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the z-plane surface, the
        half-spaces are unbounded in their x- and y- directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, self.z0]))
        elif side == '+':
            return (np.array([-np.inf, -np.inf, self.z0]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`z' - z_0`

        """
        return point[2] - self.z0


@add_metaclass(ABCMeta)
class Cylinder(Surface):
    """A cylinder whose length is parallel to the x-, y-, or z-axis.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    R : float, optional
        Radius of the cylinder. Defaults to 1.
    name : str, optional
        Name of the cylinder. If not specified, the name will be the empty
        string.

    Attributes
    ----------
    r : float
        Radius of the cylinder
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """
    def __init__(self, surface_id=None, boundary_type='transmission',
                 R=1., name=''):
        super(Cylinder, self).__init__(surface_id, boundary_type, name=name)

        self._coeff_keys = ['R']
        self.r = R

    @property
    def r(self):
        return self.coefficients['R']

    @r.setter
    def r(self, R):
        check_type('R coefficient', R, Real)
        self._coefficients['R'] = R


class XCylinder(Cylinder):
    """An infinite cylinder whose length is parallel to the x-axis of the form
    :math:`(y - y_0)^2 + (z - z_0)^2 = R^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    y0 : float, optional
        y-coordinate of the center of the cylinder. Defaults to 0.
    z0 : float, optional
        z-coordinate of the center of the cylinder. Defaults to 0.
    R : float, optional
        Radius of the cylinder. Defaults to 0.
    name : str, optional
        Name of the cylinder. If not specified, the name will be the empty
        string.

    Attributes
    ----------
    y0 : float
        y-coordinate of the center of the cylinder
    z0 : float
        z-coordinate of the center of the cylinder
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 y0=0., z0=0., R=1., name=''):
        super(XCylinder, self).__init__(surface_id, boundary_type, R, name=name)

        self._type = 'x-cylinder'
        self._coeff_keys = ['y0', 'z0', 'R']
        self.y0 = y0
        self.z0 = z0

    @property
    def y0(self):
        return self.coefficients['y0']

    @property
    def z0(self):
        return self.coefficients['z0']

    @y0.setter
    def y0(self, y0):
        check_type('y0 coefficient', y0, Real)
        self._coefficients['y0'] = y0

    @z0.setter
    def z0(self, z0):
        check_type('z0 coefficient', z0, Real)
        self._coefficients['z0'] = z0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the x-cylinder surface,
        the negative half-space is unbounded in the x- direction and the
        positive half-space is unbounded in all directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([-np.inf, self.y0 - self.r, self.z0 - self.r]),
                    np.array([np.inf, self.y0 + self.r, self.z0 + self.r]))
        elif side == '+':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(y' - y_0)^2 + (z' - z_0)^2 - R^2`

        """
        y = point[1] - self.y0
        z = point[2] - self.z0
        return y**2 + z**2 - self.r**2


class YCylinder(Cylinder):
    """An infinite cylinder whose length is parallel to the y-axis of the form
    :math:`(x - x_0)^2 + (z - z_0)^2 = R^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the center of the cylinder. Defaults to 0.
    z0 : float, optional
        z-coordinate of the center of the cylinder. Defaults to 0.
    R : float, optional
        Radius of the cylinder. Defaults to 1.
    name : str, optional
        Name of the cylinder. If not specified, the name will be the empty
        string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the center of the cylinder
    z0 : float
        z-coordinate of the center of the cylinder
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., z0=0., R=1., name=''):
        super(YCylinder, self).__init__(surface_id, boundary_type, R, name=name)

        self._type = 'y-cylinder'
        self._coeff_keys = ['x0', 'z0', 'R']
        self.x0 = x0
        self.z0 = z0

    @property
    def x0(self):
        return self.coefficients['x0']

    @property
    def z0(self):
        return self.coefficients['z0']

    @x0.setter
    def x0(self, x0):
        check_type('x0 coefficient', x0, Real)
        self._coefficients['x0'] = x0

    @z0.setter
    def z0(self, z0):
        check_type('z0 coefficient', z0, Real)
        self._coefficients['z0'] = z0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the y-cylinder surface,
        the negative half-space is unbounded in the y- direction and the
        positive half-space is unbounded in all directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([self.x0 - self.r, -np.inf, self.z0 - self.r]),
                    np.array([self.x0 + self.r, np.inf, self.z0 + self.r]))
        elif side == '+':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(x' - x_0)^2 + (z' - z_0)^2 - R^2`

        """
        x = point[0] - self.x0
        z = point[2] - self.z0
        return x**2 + z**2 - self.r**2


class ZCylinder(Cylinder):
    """An infinite cylinder whose length is parallel to the z-axis of the form
    :math:`(x - x_0)^2 + (y - y_0)^2 = R^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the center of the cylinder. Defaults to 0.
    y0 : float, optional
        y-coordinate of the center of the cylinder. Defaults to 0.
    R : float, optional
        Radius of the cylinder. Defaults to 1.
    name : str, optional
        Name of the cylinder. If not specified, the name will be the empty
        string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the center of the cylinder
    y0 : float
        y-coordinate of the center of the cylinder
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., R=1., name=''):
        super(ZCylinder, self).__init__(surface_id, boundary_type, R, name=name)

        self._type = 'z-cylinder'
        self._coeff_keys = ['x0', 'y0', 'R']
        self.x0 = x0
        self.y0 = y0

    @property
    def x0(self):
        return self.coefficients['x0']

    @property
    def y0(self):
        return self.coefficients['y0']

    @x0.setter
    def x0(self, x0):
        check_type('x0 coefficient', x0, Real)
        self._coefficients['x0'] = x0

    @y0.setter
    def y0(self, y0):
        check_type('y0 coefficient', y0, Real)
        self._coefficients['y0'] = y0

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. For the z-cylinder surface,
        the negative half-space is unbounded in the z- direction and the
        positive half-space is unbounded in all directions. To represent
        infinity, numpy.inf is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([self.x0 - self.r, self.y0 - self.r, -np.inf]),
                    np.array([self.x0 + self.r, self.y0 + self.r, np.inf]))
        elif side == '+':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(x' - x_0)^2 + (y' - y_0)^2 - R^2`

        """
        x = point[0] - self.x0
        y = point[1] - self.y0
        return x**2 + y**2 - self.r**2


class Sphere(Surface):
    """A sphere of the form :math:`(x - x_0)^2 + (y - y_0)^2 + (z - z_0)^2 = R^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the center of the sphere. Defaults to 0.
    y0 : float, optional
        y-coordinate of the center of the sphere. Defaults to 0.
    z0 : float, optional
        z-coordinate of the center of the sphere. Defaults to 0.
    R : float, optional
        Radius of the sphere. Defaults to 1.
    name : str, optional
        Name of the sphere. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the center of the sphere
    y0 : float
        y-coordinate of the center of the sphere
    z0 : float
        z-coordinate of the center of the sphere
    R : float
        Radius of the sphere
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., z0=0., R=1., name=''):
        super(Sphere, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'sphere'
        self._coeff_keys = ['x0', 'y0', 'z0', 'R']
        self.x0 = x0
        self.y0 = y0
        self.z0 = z0
        self.r = R

    @property
    def x0(self):
        return self.coefficients['x0']

    @property
    def y0(self):
        return self.coefficients['y0']

    @property
    def z0(self):
        return self.coefficients['z0']

    @property
    def r(self):
        return self.coefficients['R']

    @x0.setter
    def x0(self, x0):
        check_type('x0 coefficient', x0, Real)
        self._coefficients['x0'] = x0

    @y0.setter
    def y0(self, y0):
        check_type('y0 coefficient', y0, Real)
        self._coefficients['y0'] = y0

    @z0.setter
    def z0(self, z0):
        check_type('z0 coefficient', z0, Real)
        self._coefficients['z0'] = z0

    @r.setter
    def r(self, R):
        check_type('R coefficient', R, Real)
        self._coefficients['R'] = R

    def bounding_box(self, side):
        """Determine an axis-aligned bounding box.

        An axis-aligned bounding box for surface half-spaces is represented by
        its lower-left and upper-right coordinates. The positive half-space of a
        sphere is unbounded in all directions. To represent infinity, numpy.inf
        is used.

        Parameters
        ----------
        side : {'+', '-'}
            Indicates the negative or positive half-space

        Returns
        -------
        numpy.ndarray
            Lower-left coordinates of the axis-aligned bounding box for the
            desired half-space
        numpy.ndarray
            Upper-right coordinates of the axis-aligned bounding box for the
            desired half-space

        """

        if side == '-':
            return (np.array([self.x0 - self.r, self.y0 - self.r,
                              self.z0 - self.r]),
                    np.array([self.x0 + self.r, self.y0 + self.r,
                              self.z0 + self.r]))
        elif side == '+':
            return (np.array([-np.inf, -np.inf, -np.inf]),
                    np.array([np.inf, np.inf, np.inf]))

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(x' - x_0)^2 + (y' - y_0)^2 + (z' - z_0)^2 - R^2`

        """
        x = point[0] - self.x0
        y = point[1] - self.y0
        z = point[2] - self.z0
        return x**2 + y**2 + z**2 - self.r**2

@add_metaclass(ABCMeta)
class Cone(Surface):
    """A conical surface parallel to the x-, y-, or z-axis.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the apex. Defaults to 0.
    y0 : float
        y-coordinate of the apex. Defaults to 0.
    z0 : float
        z-coordinate of the apex. Defaults to 0.
    R2 : float
        Parameter related to the aperature. Defaults to 1.
    name : str
        Name of the cone. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the apex
    y0 : float
        y-coordinate of the apex
    z0 : float
        z-coordinate of the apex
    R2 : float
        Parameter related to the aperature
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """
    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., z0=0., R2=1., name=''):
        super(Cone, self).__init__(surface_id, boundary_type, name=name)

        self._coeff_keys = ['x0', 'y0', 'z0', 'R2']
        self.x0 = x0
        self.y0 = y0
        self.z0 = z0
        self.r2 = R2

    @property
    def x0(self):
        return self.coefficients['x0']

    @property
    def y0(self):
        return self.coefficients['y0']

    @property
    def z0(self):
        return self.coefficients['z0']

    @property
    def r2(self):
        return self.coefficients['r2']

    @x0.setter
    def x0(self, x0):
        check_type('x0 coefficient', x0, Real)
        self._coefficients['x0'] = x0

    @y0.setter
    def y0(self, y0):
        check_type('y0 coefficient', y0, Real)
        self._coefficients['y0'] = y0

    @z0.setter
    def z0(self, z0):
        check_type('z0 coefficient', z0, Real)
        self._coefficients['z0'] = z0

    @r2.setter
    def r2(self, R2):
        check_type('R^2 coefficient', R2, Real)
        self._coefficients['R2'] = R2


class XCone(Cone):
    """A cone parallel to the x-axis of the form :math:`(y - y_0)^2 + (z - z_0)^2 =
    R^2 (x - x_0)^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the apex. Defaults to 0.
    y0 : float, optional
        y-coordinate of the apex. Defaults to 0.
    z0 : float, optional
        z-coordinate of the apex. Defaults to 0.
    R2 : float, optional
        Parameter related to the aperature. Defaults to 1.
    name : str, optional
        Name of the cone. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the apex
    y0 : float
        y-coordinate of the apex
    z0 : float
        z-coordinate of the apex
    R2 : float
        Parameter related to the aperature
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., z0=0., R2=1., name=''):
        super(XCone, self).__init__(surface_id, boundary_type, x0, y0,
                                    z0, R2, name=name)

        self._type = 'x-cone'

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(y' - y_0)^2 + (z' - z_0)^2 - R^2(x' - x_0)^2`

        """
        x = point[0] - self.x0
        y = point[1] - self.y0
        z = point[2] - self.z0
        return y**2 + z**2 - self.r2*x**2


class YCone(Cone):
    """A cone parallel to the y-axis of the form :math:`(x - x_0)^2 + (z - z_0)^2 =
    R^2 (y - y_0)^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the apex. Defaults to 0.
    y0 : float, optional
        y-coordinate of the apex. Defaults to 0.
    z0 : float, optional
        z-coordinate of the apex. Defaults to 0.
    R2 : float, optional
        Parameter related to the aperature. Defaults to 1.
    name : str, optional
        Name of the cone. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the apex
    y0 : float
        y-coordinate of the apex
    z0 : float
        z-coordinate of the apex
    R2 : float
        Parameter related to the aperature
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., z0=0., R2=1., name=''):
        super(YCone, self).__init__(surface_id, boundary_type, x0, y0, z0,
                                    R2, name=name)

        self._type = 'y-cone'

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(x' - x_0)^2 + (z' - z_0)^2 - R^2(y' - y_0)^2`

        """
        x = point[0] - self.x0
        y = point[1] - self.y0
        z = point[2] - self.z0
        return x**2 + z**2 - self.r2*y**2


class ZCone(Cone):
    """A cone parallel to the x-axis of the form :math:`(x - x_0)^2 + (y - y_0)^2 =
    R^2 (z - z_0)^2`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    x0 : float, optional
        x-coordinate of the apex. Defaults to 0.
    y0 : float, optional
        y-coordinate of the apex. Defaults to 0.
    z0 : float, optional
        z-coordinate of the apex. Defaults to 0.
    R2 : float, optional
        Parameter related to the aperature. Defaults to 1.
    name : str, optional
        Name of the cone. If not specified, the name will be the empty string.

    Attributes
    ----------
    x0 : float
        x-coordinate of the apex
    y0 : float
        y-coordinate of the apex
    z0 : float
        z-coordinate of the apex
    R2 : float
        Parameter related to the aperature
    boundary_type : {'transmission, 'vacuum', 'reflective'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 x0=0., y0=0., z0=0., R2=1., name=''):
        super(ZCone, self).__init__(surface_id, boundary_type, x0, y0, z0,
                                    R2, name=name)

        self._type = 'z-cone'

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`(x' - x_0)^2 + (y' - y_0)^2 - R^2(z' - z_0)^2`

        """
        x = point[0] - self.x0
        y = point[1] - self.y0
        z = point[2] - self.z0
        return x**2 + y**2 - self.r2*z**2


class Quadric(Surface):
    """A surface of the form :math:`Ax^2 + By^2 + Cz^2 + Dxy + Eyz + Fxz + Gx + Hy +
    Jz + K = 0`.

    Parameters
    ----------
    surface_id : int, optional
        Unique identifier for the surface. If not specified, an identifier will
        automatically be assigned.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}, optional
        Boundary condition that defines the behavior for particles hitting the
        surface. Defaults to transmissive boundary condition where particles
        freely pass through the surface.
    a, b, c, d, e, f, g, h, j, k : float, optional
        coefficients for the surface. All default to 0.
    name : str, optional
        Name of the sphere. If not specified, the name will be the empty string.

    Attributes
    ----------
    a, b, c, d, e, f, g, h, j, k : float
        coefficients for the surface
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surface.
    coefficients : dict
        Dictionary of surface coefficients
    id : int
        Unique identifier for the surface
    name : str
        Name of the surface
    type : str
        Type of the surface

    """

    def __init__(self, surface_id=None, boundary_type='transmission',
                 a=0., b=0., c=0., d=0., e=0., f=0., g=0.,
                 h=0., j=0., k=0., name=''):
        super(Quadric, self).__init__(surface_id, boundary_type, name=name)

        self._type = 'quadric'
        self._coeff_keys = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k']
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
        self.g = g
        self.h = h
        self.j = j
        self.k = k

    @property
    def a(self):
        return self.coefficients['a']

    @property
    def b(self):
        return self.coefficients['b']

    @property
    def c(self):
        return self.coefficients['c']

    @property
    def d(self):
        return self.coefficients['d']

    @property
    def e(self):
        return self.coefficients['e']

    @property
    def f(self):
        return self.coefficients['f']

    @property
    def g(self):
        return self.coefficients['g']

    @property
    def h(self):
        return self.coefficients['h']

    @property
    def j(self):
        return self.coefficients['j']

    @property
    def k(self):
        return self.coefficients['k']

    @a.setter
    def a(self, a):
        check_type('a coefficient', a, Real)
        self._coefficients['a'] = a

    @b.setter
    def b(self, b):
        check_type('b coefficient', b, Real)
        self._coefficients['b'] = b

    @c.setter
    def c(self, c):
        check_type('c coefficient', c, Real)
        self._coefficients['c'] = c

    @d.setter
    def d(self, d):
        check_type('d coefficient', d, Real)
        self._coefficients['d'] = d

    @e.setter
    def e(self, e):
        check_type('e coefficient', e, Real)
        self._coefficients['e'] = e

    @f.setter
    def f(self, f):
        check_type('f coefficient', f, Real)
        self._coefficients['f'] = f

    @g.setter
    def g(self, g):
        check_type('g coefficient', g, Real)
        self._coefficients['g'] = g

    @h.setter
    def h(self, h):
        check_type('h coefficient', h, Real)
        self._coefficients['h'] = h

    @j.setter
    def j(self, j):
        check_type('j coefficient', j, Real)
        self._coefficients['j'] = j

    @k.setter
    def k(self, k):
        check_type('k coefficient', k, Real)
        self._coefficients['k'] = k

    def evaluate(self, point):
        """Evaluate the surface equation at a given point.

        Parameters
        ----------
        point : 3-tuple of float
            The Cartesian coordinates, :math:`(x',y',z')`, at which the surface
            equation should be evaluated.

        Returns
        -------
        float
            :math:`Ax'^2 + By'^2 + Cz'^2 + Dx'y' + Ey'z' + Fx'z' + Gx' + Hy' +
            Jz' + K = 0`

        """
        x, y, z = point
        return x*(self.a*x + self.d*y + self.g) + \
            y*(self.b*y + self.e*z + self.h) + \
            z*(self.c*z + self.f*x + self.j) + self.k


class Halfspace(Region):
    """A positive or negative half-space region.

    A half-space is either of the two parts into which a two-dimension surface
    divides the three-dimensional Euclidean space. If the equation of the
    surface is :math:`f(x,y,z) = 0`, the region for which :math:`f(x,y,z) < 0`
    is referred to as the negative half-space and the region for which
    :math:`f(x,y,z) > 0` is referred to as the positive half-space.

    Instances of Halfspace are generally not instantiated directly. Rather, they
    can be created from an existing Surface through the __neg__ and __pos__
    operators, as the following example demonstrates:

    >>> sphere = openmc.Sphere(surface_id=1, R=10.0)
    >>> inside_sphere = -sphere
    >>> outside_sphere = +sphere
    >>> type(inside_sphere)
    <class 'openmc.surface.Halfspace'>

    Parameters
    ----------
    surface : openmc.Surface
        Surface which divides Euclidean space.
    side : {'+', '-'}
        Indicates whether the positive or negative half-space is used.

    Attributes
    ----------
    surface : openmc.Surface
        Surface which divides Euclidean space.
    side : {'+', '-'}
        Indicates whether the positive or negative half-space is used.
    bounding_box : tuple of numpy.ndarray
        Lower-left and upper-right coordinates of an axis-aligned bounding box

    """

    def __init__(self, surface, side):
        self.surface = surface
        self.side = side

    def __and__(self, other):
        if isinstance(other, Intersection):
            return Intersection(self, *other.nodes)
        else:
            return Intersection(self, other)

    def __or__(self, other):
        if isinstance(other, Union):
            return Union(self, *other.nodes)
        else:
            return Union(self, other)

    def __invert__(self):
        return -self.surface if self.side == '+' else +self.surface

    def __contains__(self, point):
        """Check whether a point is contained in the half-space.

        Parameters
        ----------
        point : 3-tuple of float
            Cartesian coordinates, :math:`(x',y',z')`, of the point

        Returns
        -------
        bool
            Whether the point is in the half-space

        """

        val = self.surface.evaluate(point)
        return val >= 0. if self.side == '+' else val < 0.

    @property
    def surface(self):
        return self._surface

    @surface.setter
    def surface(self, surface):
        check_type('surface', surface, Surface)
        self._surface = surface

    @property
    def side(self):
        return self._side

    @side.setter
    def side(self, side):
        check_value('side', side, ('+', '-'))
        self._side = side

    @property
    def bounding_box(self):
        return self.surface.bounding_box(self.side)

    def __str__(self):
        return '-' + str(self.surface.id) if self.side == '-' \
            else str(self.surface.id)


def get_rectangular_prism(width, height, axis='z', origin=(0., 0.),
                          boundary_type='transmission'):
    """Get an infinite rectangular prism from four planar surfaces.

    Parameters
    ----------
    width: float
        Prism width in units of cm. The width is aligned with the y, x,
        or x axes for prisms parallel to the x, y, or z axis, respectively.
    height: float
        Prism height in units of cm. The height is aligned with the z, z,
        or y axes for prisms parallel to the x, y, or z axis, respectively.
    axis : {'x', 'y', 'z'}
        Axis with which the infinite length of the prism should be aligned.
        Defaults to 'z'.
    origin: Iterable of two floats
        Origin of the prism. The two floats correspond to (y,z), (x,z) or
        (x,y) for prisms parallel to the x, y or z axis, respectively.
        Defaults to (0., 0.).
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surfaces comprising the rectangular prism (default is 'transmission').

    Returns
    -------
    openmc.Region
        The inside of a rectangular prism

    """

    check_type('width', width, Real)
    check_type('height', height, Real)
    check_value('axis', axis, ['x','y','z'])
    check_type('origin', origin, Iterable, Real)

    if axis == 'x':
        min_y = YPlane(name='minimum y', y0=-width/2.+origin[0],
                       boundary_type=boundary_type)
        max_y = YPlane(name='maximum y', y0=+width/2.+origin[0],
                       boundary_type=boundary_type)
        min_z = ZPlane(name='minimum z', z0=-height/2.+origin[1],
                       boundary_type=boundary_type)
        max_z = ZPlane(name='maximum z', z0=+height/2.+origin[1],
                       boundary_type=boundary_type)
        prism = +min_y & -max_y & +min_z & -max_z
    elif axis == 'y':
        min_x = XPlane(name='minimum x', x0=-width/2.+origin[0],
                       boundary_type=boundary_type)
        max_x = XPlane(name='maximum x', x0=+width/2.+origin[0],
                       boundary_type=boundary_type)
        min_z = ZPlane(name='minimum z', z0=-height/2.+origin[1],
                       boundary_type=boundary_type)
        max_z = ZPlane(name='maximum z', z0=+height/2.+origin[1],
                       boundary_type=boundary_type)
        prism = +min_x & -max_x & +min_z & -max_z
    else:
        min_x = XPlane(name='minimum x', x0=-width/2.+origin[0],
                       boundary_type=boundary_type)
        max_x = XPlane(name='maximum x', x0=+width/2.+origin[0],
                       boundary_type=boundary_type)
        min_y = YPlane(name='minimum y', y0=-height/2.+origin[1],
                       boundary_type=boundary_type)
        max_y = YPlane(name='maximum y', y0=+height/2.+origin[1],
                       boundary_type=boundary_type)
        prism = +min_x & -max_x & +min_y & -max_y

    return prism


def get_hexagonal_prism(edge_length=1., orientation='y',
                        boundary_type='transmission'):
    """Create a hexagon region from six surface planes.

    Parameters
    ----------
    edge_length : float
        Length of a side of the hexagon in cm
    orientation : {'x', 'y'}
        An 'x' orientation means that two sides of the hexagon are parallel to
        the x-axis and a 'y' orientation means that two sides of the hexagon are
        parallel to the y-axis.
    boundary_type : {'transmission, 'vacuum', 'reflective', 'periodic'}
        Boundary condition that defines the behavior for particles hitting the
        surfaces comprising the hexagonal prism (default is 'transmission').

    Returns
    -------
    openmc.Region
        The inside of a hexagonal prism

    """

    l = edge_length

    if orientation == 'y':
        right = XPlane(x0=sqrt(3.)/2.*l)
        left = XPlane(x0=-sqrt(3.)/2.*l)
        c = sqrt(3.)/3.

        # y = -x/sqrt(3) + a
        upper_right = Plane(A=c, B=1., D=l, boundary_type=boundary_type)

        # y = x/sqrt(3) + a
        upper_left = Plane(A=-c, B=1., D=l, boundary_type=boundary_type)

        # y = x/sqrt(3) - a
        lower_right = Plane(A=-c, B=1., D=-l, boundary_type=boundary_type)

        # y = -x/sqrt(3) - a
        lower_left = Plane(A=c, B=1., D=-l, boundary_type=boundary_type)
        return Intersection(-right, +left, -upper_right, -upper_left,
                            +lower_right, +lower_left)

    elif orientation == 'x':
        top = YPlane(y0=sqrt(3.)/2.*l)
        bottom = YPlane(y0=-sqrt(3.)/2.*l)
        c = sqrt(3.)

        # y = -sqrt(3)*(x - a)
        upper_right = Plane(A=c, B=1., D=c*l, boundary_type=boundary_type)

        # y = sqrt(3)*(x + a)
        lower_right = Plane(A=-c, B=1., D=-c*l, boundary_type=boundary_type)

        # y = -sqrt(3)*(x + a)
        lower_left = Plane(A=c, B=1., D=-c*l, boundary_type=boundary_type)

        # y = sqrt(3)*(x + a)
        upper_left = Plane(A=-c, B=1., D=c*l, boundary_type=boundary_type)
        return Intersection(-top, +bottom, -upper_right, +lower_right,
                            +lower_left, -upper_left)