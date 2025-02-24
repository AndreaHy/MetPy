# Copyright (c) 2016,2017,2018 MetPy Developers.
# Distributed under the terms of the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause
"""Test the `tools` module."""

from collections import namedtuple

import numpy as np
import numpy.ma as ma
import pandas as pd
import pytest
import xarray as xr


from metpy.calc import (find_bounding_indices, find_intersections, first_derivative, get_layer,
                        get_layer_heights, gradient, grid_deltas_from_dataarray, interp,
                        interpolate_nans, laplacian, lat_lon_grid_deltas, log_interp,
                        nearest_intersection_idx, parse_angle, pressure_to_height_std,
                        reduce_point_density, resample_nn_1d, second_derivative)
from metpy.calc.tools import (_delete_masked_points, _get_bound_pressure_height,
                              _greater_or_close, _less_or_close, _next_non_masked_element,
                              DIR_STRS)
from metpy.deprecation import MetpyDeprecationWarning
from metpy.testing import (assert_almost_equal, assert_array_almost_equal, assert_array_equal,
                           check_and_silence_deprecation)
from metpy.units import units


def test_resample_nn():
    """Test 1d nearest neighbor functionality."""
    a = np.arange(5.)
    b = np.array([2, 3.8])
    truth = np.array([2, 4])

    assert_array_equal(truth, resample_nn_1d(a, b))


def test_nearest_intersection_idx():
    """Test nearest index to intersection functionality."""
    x = np.linspace(5, 30, 17)
    y1 = 3 * x**2
    y2 = 100 * x - 650
    truth = np.array([2, 12])

    assert_array_equal(truth, nearest_intersection_idx(y1, y2))


@pytest.mark.parametrize('direction, expected', [
    ('all', np.array([[8.88, 24.44], [238.84, 1794.53]])),
    ('increasing', np.array([[24.44], [1794.53]])),
    ('decreasing', np.array([[8.88], [238.84]]))
])
def test_find_intersections(direction, expected):
    """Test finding the intersection of two curves functionality."""
    x = np.linspace(5, 30, 17)
    y1 = 3 * x**2
    y2 = 100 * x - 650
    # Note: Truth is what we will get with this sampling, not the mathematical intersection
    assert_array_almost_equal(expected, find_intersections(x, y1, y2, direction=direction), 2)


def test_find_intersections_no_intersections():
    """Test finding the intersection of two curves with no intersections."""
    x = np.linspace(5, 30, 17)
    y1 = 3 * x + 0
    y2 = 5 * x + 5
    # Note: Truth is what we will get with this sampling, not the mathematical intersection
    truth = np.array([[],
                      []])
    assert_array_equal(truth, find_intersections(x, y1, y2))


def test_find_intersections_invalid_direction():
    """Test exception if an invalid direction is given."""
    x = np.linspace(5, 30, 17)
    y1 = 3 * x ** 2
    y2 = 100 * x - 650
    with pytest.raises(ValueError):
        find_intersections(x, y1, y2, direction='increaing')


def test_find_intersections_units():
    """Test handling of units when logarithmic interpolation is called."""
    x = np.linspace(5, 30, 17) * units.hPa
    y1 = 3 * x.m**2
    y2 = 100 * x.m - 650
    truth = np.array([24.43, 1794.54])
    x_test, y_test = find_intersections(x, y1, y2, direction='increasing', log_x=True)
    assert_array_almost_equal(truth, np.array([x_test.m, y_test.m]).flatten(), 2)
    assert x_test.units == units.hPa


@pytest.mark.parametrize('direction, expected', [
    ('all', np.array([[0., 3.5, 4.33333333, 7., 9., 10., 11.5, 13.], np.zeros(8)])),
    ('increasing', np.array([[0., 4.333, 7., 11.5], np.zeros(4)])),
    ('decreasing', np.array([[3.5, 10.], np.zeros(2)]))
])
def test_find_intersections_intersections_in_data_at_ends(direction, expected):
    """Test finding intersections when intersections are in the data.

    Test data includes points of intersection, sequential points of intersection, intersection
    at the ends of the data, and intersections in increasing/decreasing direction.
    """
    x = np.arange(14)
    y1 = np.array([0, 3, 2, 1, -1, 2, 2, 0, 1, 0, 0, -2, 2, 0])
    y2 = np.zeros_like(y1)
    assert_array_almost_equal(expected, find_intersections(x, y1, y2, direction=direction), 2)


@check_and_silence_deprecation
def test_interpolate_nan_linear():
    """Test deprecated interpolate_nans function."""
    x = np.linspace(0, 20, 15)
    y = 5 * x + 3
    nan_indexes = [1, 5, 11, 12]
    y_with_nan = y.copy()
    y_with_nan[nan_indexes] = np.nan
    assert_array_almost_equal(y, interpolate_nans(x, y_with_nan), 2)


@pytest.mark.parametrize('mask, expected_idx, expected_element', [
    ([False, False, False, False, False], 1, 1),
    ([False, True, True, False, False], 3, 3),
    ([False, True, True, True, True], None, None)
])
def test_non_masked_elements(mask, expected_idx, expected_element):
    """Test with a valid element."""
    a = ma.masked_array(np.arange(5), mask=mask)
    idx, element = _next_non_masked_element(a, 1)
    assert idx == expected_idx
    assert element == expected_element


@pytest.fixture
def thin_point_data():
    r"""Provide scattered points for testing."""
    xy = np.array([[0.8793620, 0.9005706], [0.5382446, 0.8766988], [0.6361267, 0.1198620],
                   [0.4127191, 0.0270573], [0.1486231, 0.3121822], [0.2607670, 0.4886657],
                   [0.7132257, 0.2827587], [0.4371954, 0.5660840], [0.1318544, 0.6468250],
                   [0.6230519, 0.0682618], [0.5069460, 0.2326285], [0.1324301, 0.5609478],
                   [0.7975495, 0.2109974], [0.7513574, 0.9870045], [0.9305814, 0.0685815],
                   [0.5271641, 0.7276889], [0.8116574, 0.4795037], [0.7017868, 0.5875983],
                   [0.5591604, 0.5579290], [0.1284860, 0.0968003], [0.2857064, 0.3862123]])
    return xy


@pytest.mark.parametrize('radius, truth',
                         [(2.0, np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.bool)),
                          (1.0, np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 0, 0, 0, 0, 0, 1, 0], dtype=np.bool)),
                          (0.3, np.array([1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0,
                                          0, 0, 0, 0, 0, 1, 0, 0, 0, 0], dtype=np.bool)),
                          (0.1, np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1,
                                          0, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.bool))
                          ])
def test_reduce_point_density(thin_point_data, radius, truth):
    r"""Test that reduce_point_density works."""
    assert_array_equal(reduce_point_density(thin_point_data, radius=radius), truth)


@pytest.mark.parametrize('radius, truth',
                         [(2.0, np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.bool)),
                          (1.0, np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 0, 0, 0, 0, 0, 1, 0], dtype=np.bool)),
                          (0.3, np.array([1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0,
                                          0, 0, 0, 0, 0, 1, 0, 0, 0, 0], dtype=np.bool)),
                          (0.1, np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1,
                                          0, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.bool))
                          ])
def test_reduce_point_density_units(thin_point_data, radius, truth):
    r"""Test that reduce_point_density works with units."""
    assert_array_equal(reduce_point_density(thin_point_data * units.dam,
                                            radius=radius * units.dam), truth)


@pytest.mark.parametrize('radius, truth',
                         [(2.0, np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 0, 0, 0, 0, 0, 0, 1], dtype=np.bool)),
                          (0.7, np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                          0, 0, 0, 1, 0, 0, 0, 0, 0, 1], dtype=np.bool)),
                          (0.3, np.array([1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0,
                                          0, 0, 0, 1, 0, 0, 0, 1, 0, 1], dtype=np.bool)),
                          (0.1, np.array([1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1,
                                          0, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.bool))
                          ])
def test_reduce_point_density_priority(thin_point_data, radius, truth):
    r"""Test that reduce_point_density works properly with priority."""
    key = np.array([8, 6, 2, 8, 6, 4, 4, 8, 8, 6, 3, 4, 3, 0, 7, 4, 3, 2, 3, 3, 9])
    assert_array_equal(reduce_point_density(thin_point_data, radius, key), truth)


def test_reduce_point_density_1d():
    r"""Test that reduce_point_density works with 1D points."""
    x = np.array([1, 3, 4, 8, 9, 10])
    assert_array_equal(reduce_point_density(x, 2.5),
                       np.array([1, 0, 1, 1, 0, 0], dtype=np.bool))


def test_delete_masked_points():
    """Test deleting masked points."""
    a = ma.masked_array(np.arange(5), mask=[False, True, False, False, False])
    b = ma.masked_array(np.arange(5), mask=[False, False, False, True, False])
    expected = np.array([0, 2, 4])
    a, b = _delete_masked_points(a, b)
    assert_array_equal(a, expected)
    assert_array_equal(b, expected)


@check_and_silence_deprecation
def test_interp():
    """Test deprecated interp function."""
    x = np.array([1., 2., 3., 4.])
    y = x
    x_interp = np.array([3.5000000, 2.5000000])
    y_interp_truth = np.array([3.5000000, 2.5000000])
    y_interp = interp(x_interp, x, y)
    assert_array_almost_equal(y_interp, y_interp_truth, 7)


@check_and_silence_deprecation
def test_log_interp():
    """Test deprecated log_interp function."""
    x_log = np.array([1e3, 1e4, 1e5, 1e6])
    y_log = np.log(x_log) * 2 + 3
    x_interp = np.array([5e3, 5e4, 5e5])
    y_interp_truth = np.array([20.0343863828, 24.6395565688, 29.2447267548])
    y_interp = log_interp(x_interp, x_log, y_log)
    assert_array_almost_equal(y_interp, y_interp_truth, 7)


def get_bounds_data():
    """Provide pressure and height data for testing layer bounds calculation."""
    pressures = np.linspace(1000, 100, 10) * units.hPa
    heights = pressure_to_height_std(pressures)
    return pressures, heights


@pytest.mark.parametrize('pressure, bound, hgts, interp, expected', [
    (get_bounds_data()[0], 900 * units.hPa, None, True,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 900 * units.hPa, None, False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 870 * units.hPa, None, True,
     (870 * units.hPa, 1.2665298 * units.kilometer)),
    (get_bounds_data()[0], 870 * units.hPa, None, False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 0.9880028 * units.kilometer, None, True,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 0.9880028 * units.kilometer, None, False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 1.2665298 * units.kilometer, None, True,
     (870 * units.hPa, 1.2665298 * units.kilometer)),
    (get_bounds_data()[0], 1.2665298 * units.kilometer, None, False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 900 * units.hPa, get_bounds_data()[1], True,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 900 * units.hPa, get_bounds_data()[1], False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 870 * units.hPa, get_bounds_data()[1], True,
     (870 * units.hPa, 1.2643214 * units.kilometer)),
    (get_bounds_data()[0], 870 * units.hPa, get_bounds_data()[1], False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 0.9880028 * units.kilometer, get_bounds_data()[1], True,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 0.9880028 * units.kilometer, get_bounds_data()[1], False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 1.2665298 * units.kilometer, get_bounds_data()[1], True,
     (870.9869087 * units.hPa, 1.2665298 * units.kilometer)),
    (get_bounds_data()[0], 1.2665298 * units.kilometer, get_bounds_data()[1], False,
     (900 * units.hPa, 0.9880028 * units.kilometer)),
    (get_bounds_data()[0], 0.98800289 * units.kilometer, get_bounds_data()[1], True,
     (900 * units.hPa, 0.9880028 * units.kilometer))
])
def test_get_bound_pressure_height(pressure, bound, hgts, interp, expected):
    """Test getting bounds in layers with various parameter combinations."""
    bounds = _get_bound_pressure_height(pressure, bound, heights=hgts, interpolate=interp)
    assert_array_almost_equal(bounds[0], expected[0], 4)
    assert_array_almost_equal(bounds[1], expected[1], 4)


def test_get_bound_invalid_bound_units():
    """Test that value error is raised with invalid bound units."""
    p = np.arange(900, 300, -100) * units.hPa
    with pytest.raises(ValueError):
        _get_bound_pressure_height(p, 100 * units.degC)


def test_get_bound_pressure_out_of_range():
    """Test when bound is out of data range in pressure."""
    p = np.arange(900, 300, -100) * units.hPa
    with pytest.raises(ValueError):
        _get_bound_pressure_height(p, 100 * units.hPa)
    with pytest.raises(ValueError):
        _get_bound_pressure_height(p, 1000 * units.hPa)


def test_get_bound_height_out_of_range():
    """Test when bound is out of data range in height."""
    p = np.arange(900, 300, -100) * units.hPa
    h = np.arange(1, 7) * units.kilometer
    with pytest.raises(ValueError):
        _get_bound_pressure_height(p, 8 * units.kilometer, heights=h)
    with pytest.raises(ValueError):
        _get_bound_pressure_height(p, 100 * units.meter, heights=h)


@pytest.mark.parametrize('flip_order', [(True, False)])
def test_get_layer_float32(flip_order):
    """Test that get_layer works properly with float32 data."""
    p = np.asarray([940.85083008, 923.78851318, 911.42022705, 896.07220459,
                    876.89404297, 781.63330078], np.float32) * units('hPa')
    hgt = np.asarray([563.671875, 700.93817139, 806.88098145, 938.51745605,
                      1105.25854492, 2075.04443359], dtype=np.float32) * units.meter

    true_p_layer = np.asarray([940.85083008, 923.78851318, 911.42022705, 896.07220459,
                               876.89404297, 831.86472819], np.float32) * units('hPa')
    true_hgt_layer = np.asarray([563.671875, 700.93817139, 806.88098145, 938.51745605,
                                 1105.25854492, 1549.8079], dtype=np.float32) * units.meter

    if flip_order:
        p = p[::-1]
        hgt = hgt[::-1]
    p_layer, hgt_layer = get_layer(p, hgt, heights=hgt, depth=1000. * units.meter)
    assert_array_almost_equal(p_layer, true_p_layer, 4)
    assert_array_almost_equal(hgt_layer, true_hgt_layer, 4)


def test_get_layer_ragged_data():
    """Test that an error is raised for unequal length pressure and data arrays."""
    p = np.arange(10) * units.hPa
    y = np.arange(9) * units.degC
    with pytest.raises(ValueError):
        get_layer(p, y)


def test_get_layer_invalid_depth_units():
    """Test that an error is raised when depth has invalid units."""
    p = np.arange(10) * units.hPa
    y = np.arange(9) * units.degC
    with pytest.raises(ValueError):
        get_layer(p, y, depth=400 * units.degC)


def layer_test_data():
    """Provide test data for testing of layer bounds."""
    pressure = np.arange(1000, 10, -100) * units.hPa
    temperature = np.linspace(25, -50, len(pressure)) * units.degC
    return pressure, temperature


@pytest.mark.parametrize('pressure, variable, heights, bottom, depth, interp, expected', [
    (layer_test_data()[0], layer_test_data()[1], None, None, 150 * units.hPa, True,
     (np.array([1000, 900, 850]) * units.hPa,
      np.array([25.0, 16.666666, 12.62262]) * units.degC)),
    (layer_test_data()[0], layer_test_data()[1], None, None, 150 * units.hPa, False,
     (np.array([1000, 900]) * units.hPa, np.array([25.0, 16.666666]) * units.degC)),
    (layer_test_data()[0], layer_test_data()[1], None, 2 * units.km, 3 * units.km, True,
     (np.array([794.85264282, 700., 600., 540.01696548]) * units.hPa,
      np.array([7.93049516, 0., -8.33333333, -13.14758845]) * units.degC))
])
def test_get_layer(pressure, variable, heights, bottom, depth, interp, expected):
    """Test get_layer functionality."""
    p_layer, y_layer = get_layer(pressure, variable, heights=heights, bottom=bottom,
                                 depth=depth, interpolate=interp)
    assert_array_almost_equal(p_layer, expected[0], 4)
    assert_array_almost_equal(y_layer, expected[1], 4)


def test_greater_or_close():
    """Test floating point greater or close to."""
    x = np.array([0.0, 1.0, 1.49999, 1.5, 1.5000, 1.7])
    comparison_value = 1.5
    truth = np.array([False, False, True, True, True, True])
    res = _greater_or_close(x, comparison_value)
    assert_array_equal(res, truth)


def test_greater_or_close_mixed_types():
    """Test _greater_or_close with mixed Quantity and array errors."""
    with pytest.raises(ValueError):
        _greater_or_close(1000. * units.mbar, 1000.)

    with pytest.raises(ValueError):
        _greater_or_close(1000., 1000. * units.mbar)


def test_less_or_close():
    """Test floating point less or close to."""
    x = np.array([0.0, 1.0, 1.49999, 1.5, 1.5000, 1.7])
    comparison_value = 1.5
    truth = np.array([True, True, True, True, True, False])
    res = _less_or_close(x, comparison_value)
    assert_array_equal(res, truth)


def test_less_or_close_mixed_types():
    """Test _less_or_close with mixed Quantity and array errors."""
    with pytest.raises(ValueError):
        _less_or_close(1000. * units.mbar, 1000.)

    with pytest.raises(ValueError):
        _less_or_close(1000., 1000. * units.mbar)


def test_get_layer_heights_interpolation():
    """Test get_layer_heights with interpolation."""
    heights = np.arange(10) * units.km
    data = heights.m * 2 * units.degC
    heights, data = get_layer_heights(heights, 5000 * units.m, data, bottom=1500 * units.m)
    heights_true = np.array([1.5, 2, 3, 4, 5, 6, 6.5]) * units.km
    data_true = heights_true.m * 2 * units.degC
    assert_array_almost_equal(heights_true, heights, 6)
    assert_array_almost_equal(data_true, data, 6)


def test_get_layer_heights_no_interpolation():
    """Test get_layer_heights without interpolation."""
    heights = np.arange(10) * units.km
    data = heights.m * 2 * units.degC
    heights, data = get_layer_heights(heights, 5000 * units.m, data,
                                      bottom=1500 * units.m, interpolate=False)
    heights_true = np.array([2, 3, 4, 5, 6]) * units.km
    data_true = heights_true.m * 2 * units.degC
    assert_array_almost_equal(heights_true, heights, 6)
    assert_array_almost_equal(data_true, data, 6)


def test_get_layer_heights_agl():
    """Test get_layer_heights with interpolation."""
    heights = np.arange(300, 1200, 100) * units.m
    data = heights.m * 0.1 * units.degC
    heights, data = get_layer_heights(heights, 500 * units.m, data, with_agl=True)
    heights_true = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5]) * units.km
    data_true = np.array([30, 40, 50, 60, 70, 80]) * units.degC
    assert_array_almost_equal(heights_true, heights, 6)
    assert_array_almost_equal(data_true, data, 6)


def test_get_layer_heights_agl_bottom_no_interp():
    """Test get_layer_heights with no interpolation and a bottom."""
    heights_init = np.arange(300, 1200, 100) * units.m
    data = heights_init.m * 0.1 * units.degC
    heights, data = get_layer_heights(heights_init, 500 * units.m, data, with_agl=True,
                                      interpolation=False, bottom=200 * units.m)
    # Regression test for #789
    assert_array_equal(heights_init[0], 300 * units.m)
    heights_true = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7]) * units.km
    data_true = np.array([50, 60, 70, 80, 90, 100]) * units.degC
    assert_array_almost_equal(heights_true, heights, 6)
    assert_array_almost_equal(data_true, data, 6)


def test_lat_lon_grid_deltas_1d():
    """Test for lat_lon_grid_deltas for variable grid."""
    lat = np.arange(40, 50, 2.5)
    lon = np.arange(-100, -90, 2.5)
    dx, dy = lat_lon_grid_deltas(lon, lat)
    dx_truth = np.array([[212943.5585, 212943.5585, 212943.5585],
                         [204946.2305, 204946.2305, 204946.2305],
                         [196558.8269, 196558.8269, 196558.8269],
                         [187797.3216, 187797.3216, 187797.3216]]) * units.meter
    dy_truth = np.array([[277987.1857, 277987.1857, 277987.1857, 277987.1857],
                         [277987.1857, 277987.1857, 277987.1857, 277987.1857],
                         [277987.1857, 277987.1857, 277987.1857, 277987.1857]]) * units.meter
    assert_almost_equal(dx, dx_truth, 4)
    assert_almost_equal(dy, dy_truth, 4)


@pytest.mark.parametrize('flip_order', [(False, True)])
def test_lat_lon_grid_deltas_2d(flip_order):
    """Test for lat_lon_grid_deltas for variable grid with negative delta distances."""
    lat = np.arange(40, 50, 2.5)
    lon = np.arange(-100, -90, 2.5)
    dx_truth = np.array([[212943.5585, 212943.5585, 212943.5585],
                         [204946.2305, 204946.2305, 204946.2305],
                         [196558.8269, 196558.8269, 196558.8269],
                         [187797.3216, 187797.3216, 187797.3216]]) * units.meter
    dy_truth = np.array([[277987.1857, 277987.1857, 277987.1857, 277987.1857],
                         [277987.1857, 277987.1857, 277987.1857, 277987.1857],
                         [277987.1857, 277987.1857, 277987.1857, 277987.1857]]) * units.meter
    if flip_order:
        lon = lon[::-1]
        lat = lat[::-1]
        dx_truth = -1 * dx_truth[::-1]
        dy_truth = -1 * dy_truth[::-1]

    lon, lat = np.meshgrid(lon, lat)
    dx, dy = lat_lon_grid_deltas(lon, lat)
    assert_almost_equal(dx, dx_truth, 4)
    assert_almost_equal(dy, dy_truth, 4)


def test_lat_lon_grid_deltas_extra_dimensions():
    """Test for lat_lon_grid_deltas with extra leading dimensions."""
    lon, lat = np.meshgrid(np.arange(-100, -90, 2.5), np.arange(40, 50, 2.5))
    lat = lat[None, None]
    lon = lon[None, None]
    dx_truth = np.array([[[[212943.5585, 212943.5585, 212943.5585],
                           [204946.2305, 204946.2305, 204946.2305],
                           [196558.8269, 196558.8269, 196558.8269],
                           [187797.3216, 187797.3216, 187797.3216]]]]) * units.meter
    dy_truth = (np.array([[[[277987.1857, 277987.1857, 277987.1857, 277987.1857],
                            [277987.1857, 277987.1857, 277987.1857, 277987.1857],
                            [277987.1857, 277987.1857, 277987.1857, 277987.1857]]]])
                * units.meter)
    dx, dy = lat_lon_grid_deltas(lon, lat)
    assert_almost_equal(dx, dx_truth, 4)
    assert_almost_equal(dy, dy_truth, 4)


def test_lat_lon_grid_deltas_mismatched_shape():
    """Test for lat_lon_grid_deltas for variable grid."""
    lat = np.arange(40, 50, 2.5)
    lon = np.array([[-100., -97.5, -95., -92.5],
                    [-100., -97.5, -95., -92.5],
                    [-100., -97.5, -95., -92.5],
                    [-100., -97.5, -95., -92.5]])
    with pytest.raises(ValueError):
        lat_lon_grid_deltas(lon, lat)


@pytest.fixture()
def deriv_1d_data():
    """Return 1-dimensional data for testing derivative functions."""
    return namedtuple('D_1D_Test_Data', 'x values')(np.array([0, 1.25, 3.75]) * units.cm,
                                                    np.array([13.5, 12, 10]) * units.degC)


@pytest.fixture()
def deriv_2d_data():
    """Return 2-dimensional data for analytic function for testing derivative functions."""
    ret = namedtuple('D_2D_Test_Data', 'x y x0 y0 a b f')(
        np.array([0., 2., 7.]), np.array([1., 5., 11., 13.]), 3, 1.5, 0.5, 0.25, 0)

    # Makes a value array with y changing along rows (axis 0) and x along columns (axis 1)
    return ret._replace(f=ret.a * (ret.x - ret.x0)**2 + ret.b * (ret.y[:, None] - ret.y0)**2)


@pytest.fixture()
def deriv_4d_data():
    """Return simple 4-dimensional data for testing axis handling of derivative functions."""
    return np.arange(3 * 3 * 4 * 4).reshape((3, 3, 4, 4))


def test_first_derivative(deriv_1d_data):
    """Test first_derivative with a simple 1D array."""
    dv_dx = first_derivative(deriv_1d_data.values, x=deriv_1d_data.x)

    # Worked by hand and taken from Chapra and Canale 23.2
    truth = np.array([-1.333333, -1.06666667, -0.5333333]) * units('delta_degC / cm')
    assert_array_almost_equal(dv_dx, truth, 5)


def test_first_derivative_2d(deriv_2d_data):
    """Test first_derivative with a full 2D array."""
    df_dx = first_derivative(deriv_2d_data.f, x=deriv_2d_data.x, axis=1)
    df_dx_analytic = np.tile(2 * deriv_2d_data.a * (deriv_2d_data.x - deriv_2d_data.x0),
                             (deriv_2d_data.f.shape[0], 1))
    assert_array_almost_equal(df_dx, df_dx_analytic, 5)

    df_dy = first_derivative(deriv_2d_data.f, x=deriv_2d_data.y, axis=0)
    # Repeat each row, then flip to get variation along rows
    df_dy_analytic = np.tile(2 * deriv_2d_data.b * (deriv_2d_data.y - deriv_2d_data.y0),
                             (deriv_2d_data.f.shape[1], 1)).T
    assert_array_almost_equal(df_dy, df_dy_analytic, 5)


def test_first_derivative_too_small(deriv_1d_data):
    """Test first_derivative with too small an array."""
    with pytest.raises(ValueError):
        first_derivative(deriv_1d_data.values[None, :].T, x=deriv_1d_data.x, axis=1)


def test_first_derivative_scalar_delta():
    """Test first_derivative with a scalar passed for a delta."""
    df_dx = first_derivative(np.arange(3), delta=1)
    assert_array_almost_equal(df_dx, np.array([1., 1., 1.]), 6)


def test_first_derivative_masked():
    """Test that first_derivative properly propagates masks."""
    data = np.ma.arange(7)
    data[3] = np.ma.masked
    df_dx = first_derivative(data, delta=1)

    truth = np.ma.array([1., 1., 1., 1., 1., 1., 1.],
                        mask=[False, False, True, True, True, False, False])
    assert_array_almost_equal(df_dx, truth)
    assert_array_equal(df_dx.mask, truth.mask)


def test_second_derivative(deriv_1d_data):
    """Test second_derivative with a simple 1D array."""
    d2v_dx2 = second_derivative(deriv_1d_data.values, x=deriv_1d_data.x)

    # Worked by hand
    truth = np.ones_like(deriv_1d_data.values) * 0.2133333 * units('delta_degC/cm**2')
    assert_array_almost_equal(d2v_dx2, truth, 5)


def test_second_derivative_2d(deriv_2d_data):
    """Test second_derivative with a full 2D array."""
    df2_dx2 = second_derivative(deriv_2d_data.f, x=deriv_2d_data.x, axis=1)
    assert_array_almost_equal(df2_dx2,
                              np.ones_like(deriv_2d_data.f) * (2 * deriv_2d_data.a), 5)

    df2_dy2 = second_derivative(deriv_2d_data.f, x=deriv_2d_data.y, axis=0)
    assert_array_almost_equal(df2_dy2,
                              np.ones_like(deriv_2d_data.f) * (2 * deriv_2d_data.b), 5)


def test_second_derivative_too_small(deriv_1d_data):
    """Test second_derivative with too small an array."""
    with pytest.raises(ValueError):
        second_derivative(deriv_1d_data.values[None, :].T, x=deriv_1d_data.x, axis=1)


def test_second_derivative_scalar_delta():
    """Test second_derivative with a scalar passed for a delta."""
    df_dx = second_derivative(np.arange(3), delta=1)
    assert_array_almost_equal(df_dx, np.array([0., 0., 0.]), 6)


def test_laplacian(deriv_1d_data):
    """Test laplacian with simple 1D data."""
    laplac = laplacian(deriv_1d_data.values, coordinates=(deriv_1d_data.x,))

    # Worked by hand
    truth = np.ones_like(deriv_1d_data.values) * 0.2133333 * units('delta_degC/cm**2')
    assert_array_almost_equal(laplac, truth, 5)


def test_laplacian_2d(deriv_2d_data):
    """Test lapacian with full 2D arrays."""
    laplac_true = 2 * (np.ones_like(deriv_2d_data.f) * (deriv_2d_data.a + deriv_2d_data.b))
    laplac = laplacian(deriv_2d_data.f, coordinates=(deriv_2d_data.y, deriv_2d_data.x))
    assert_array_almost_equal(laplac, laplac_true, 5)


def test_laplacian_x_deprecation(deriv_2d_data):
    """Test deprecation of x keyword argument."""
    laplac_true = 2 * (np.ones_like(deriv_2d_data.f) * (deriv_2d_data.a + deriv_2d_data.b))
    with pytest.warns(MetpyDeprecationWarning):
        laplac = laplacian(deriv_2d_data.f, x=(deriv_2d_data.y, deriv_2d_data.x))
    assert_array_almost_equal(laplac, laplac_true, 5)


def test_parse_angle_abbrieviated():
    """Test abbrieviated directional text in degrees."""
    expected_angles_degrees = np.arange(0, 360, 22.5) * units.degree
    output_angles_degrees = parse_angle(DIR_STRS)
    assert_array_almost_equal(output_angles_degrees, expected_angles_degrees)


def test_parse_angle_ext():
    """Test extended (unabbrieviated) directional text in degrees."""
    test_dir_strs = ['NORTH', 'NORTHnorthEast', 'North_East', 'East__North_East',
                     'easT', 'east  south east', 'south east', ' south southeast',
                     'SOUTH', 'SOUTH SOUTH WEST', 'southWEST', 'WEST south_WEST',
                     'WeSt', 'WestNorth West', 'North West', 'NORTH north_WeSt']
    expected_angles_degrees = np.arange(0, 360, 22.5) * units.degree
    output_angles_degrees = parse_angle(test_dir_strs)
    assert_array_almost_equal(output_angles_degrees, expected_angles_degrees)


def test_parse_angle_mix_multiple():
    """Test list of extended (unabbrieviated) directional text in degrees in one go."""
    test_dir_strs = ['NORTH', 'nne', 'ne', 'east north east',
                     'easT', 'east  se', 'south east', ' south southeast',
                     'SOUTH', 'SOUTH SOUTH WEST', 'sw', 'WEST south_WEST',
                     'w', 'wnw', 'North West', 'nnw']
    expected_angles_degrees = np.arange(0, 360, 22.5) * units.degree
    output_angles_degrees = parse_angle(test_dir_strs)
    assert_array_almost_equal(output_angles_degrees, expected_angles_degrees)


def test_parse_angles_array():
    """Test array of angles to parse."""
    angles = np.array(['N', 'S', 'E', 'W'])
    expected_angles = np.array([0, 180, 90, 270]) * units.degree
    calculated_angles = parse_angle(angles)
    assert_array_almost_equal(calculated_angles, expected_angles)


def test_parse_angles_series():
    """Test pandas.Series of angles to parse."""
    angles = pd.Series(['N', 'S', 'E', 'W'])
    expected_angles = np.array([0, 180, 90, 270]) * units.degree
    calculated_angles = parse_angle(angles)
    assert_array_almost_equal(calculated_angles, expected_angles)


def test_parse_angles_single():
    """Test single input into `parse_angles`."""
    calculated_angle = parse_angle('SOUTH SOUTH EAST')
    expected_angle = 157.5 * units.degree
    assert_almost_equal(calculated_angle, expected_angle)


def test_gradient_2d(deriv_2d_data):
    """Test gradient with 2D arrays."""
    res = gradient(deriv_2d_data.f, coordinates=(deriv_2d_data.y, deriv_2d_data.x))
    truth = (np.array([[-0.25, -0.25, -0.25],
                       [1.75, 1.75, 1.75],
                       [4.75, 4.75, 4.75],
                       [5.75, 5.75, 5.75]]),
             np.array([[-3, -1, 4],
                       [-3, -1, 4],
                       [-3, -1, 4],
                       [-3, -1, 4]]))
    assert_array_almost_equal(res, truth, 5)


def test_gradient_4d(deriv_4d_data):
    """Test gradient with 4D arrays."""
    res = gradient(deriv_4d_data, deltas=(1, 1, 1, 1))
    truth = tuple(factor * np.ones_like(deriv_4d_data) for factor in (48., 16., 4., 1.))
    assert_array_almost_equal(res, truth, 8)


def test_gradient_restricted_axes(deriv_2d_data):
    """Test 2D gradient with 3D arrays and manual specification of axes."""
    res = gradient(deriv_2d_data.f[..., None], coordinates=(deriv_2d_data.y, deriv_2d_data.x),
                   axes=(0, 1))
    truth = (np.array([[[-0.25], [-0.25], [-0.25]],
                       [[1.75], [1.75], [1.75]],
                       [[4.75], [4.75], [4.75]],
                       [[5.75], [5.75], [5.75]]]),
             np.array([[[-3], [-1], [4]],
                       [[-3], [-1], [4]],
                       [[-3], [-1], [4]],
                       [[-3], [-1], [4]]]))
    assert_array_almost_equal(res, truth, 5)


def test_gradient_x_deprecation(deriv_2d_data):
    """Test deprecation of x keyword argument."""
    with pytest.warns(MetpyDeprecationWarning):
        res = gradient(deriv_2d_data.f, x=(deriv_2d_data.y, deriv_2d_data.x))
    truth = (np.array([[-0.25, -0.25, -0.25],
                       [1.75, 1.75, 1.75],
                       [4.75, 4.75, 4.75],
                       [5.75, 5.75, 5.75]]),
             np.array([[-3, -1, 4],
                       [-3, -1, 4],
                       [-3, -1, 4],
                       [-3, -1, 4]]))
    assert_array_almost_equal(res, truth, 5)


def test_bounding_indices():
    """Test finding bounding indices."""
    data = np.array([[1, 2, 3, 1], [5, 6, 7, 8]])
    above, below, good = find_bounding_indices(data, [1.5, 7], axis=1, from_below=True)

    assert_array_equal(above[1], np.array([[1, 0], [0, 3]]))
    assert_array_equal(below[1], np.array([[0, -1], [-1, 2]]))
    assert_array_equal(good, np.array([[True, False], [False, True]]))


def test_bounding_indices_above():
    """Test finding bounding indices from above."""
    data = np.array([[1, 2, 3, 1], [5, 6, 7, 8]])
    above, below, good = find_bounding_indices(data, [1.5, 7], axis=1, from_below=False)

    assert_array_equal(above[1], np.array([[3, 0], [0, 3]]))
    assert_array_equal(below[1], np.array([[2, -1], [-1, 2]]))
    assert_array_equal(good, np.array([[True, False], [False, True]]))


def test_3d_gradient_3d_data_no_axes(deriv_4d_data):
    """Test 3D gradient with 3D data and no axes parameter."""
    test = deriv_4d_data[0]
    res = gradient(test, deltas=(1, 1, 1))
    truth = tuple(factor * np.ones_like(test) for factor in (16., 4., 1.))
    assert_array_almost_equal(res, truth, 8)


def test_2d_gradient_3d_data_no_axes(deriv_4d_data):
    """Test for failure of 2D gradient with 3D data and no axes parameter."""
    test = deriv_4d_data[0]
    with pytest.raises(ValueError) as exc:
        gradient(test, deltas=(1, 1))
    assert 'must match the number of dimensions' in str(exc.value)


def test_3d_gradient_2d_data_no_axes(deriv_4d_data):
    """Test for failure of 3D gradient with 2D data and no axes parameter."""
    test = deriv_4d_data[0, 0]
    with pytest.raises(ValueError) as exc:
        gradient(test, deltas=(1, 1, 1))
    assert 'must match the number of dimensions' in str(exc.value)


def test_2d_gradient_4d_data_2_axes_3_deltas(deriv_4d_data):
    """Test 2D gradient of 4D data with 2 axes and 3 deltas."""
    res = gradient(deriv_4d_data, deltas=(1, 1, 1), axes=(-2, -1))
    truth = tuple(factor * np.ones_like(deriv_4d_data) for factor in (4., 1.))
    assert_array_almost_equal(res, truth, 8)


def test_2d_gradient_4d_data_2_axes_2_deltas(deriv_4d_data):
    """Test 2D gradient of 4D data with 2 axes and 2 deltas."""
    res = gradient(deriv_4d_data, deltas=(1, 1), axes=(0, 1))
    truth = tuple(factor * np.ones_like(deriv_4d_data) for factor in (48., 16.))
    assert_array_almost_equal(res, truth, 8)


def test_2d_gradient_4d_data_2_axes_1_deltas(deriv_4d_data):
    """Test for failure of 2D gradient of 4D data with 2 axes and 1 deltas."""
    with pytest.raises(ValueError) as exc:
        gradient(deriv_4d_data, deltas=(1, ), axes=(1, 2))
    assert 'cannot be less than that of "axes"' in str(exc.value)


@pytest.fixture()
def test_da_lonlat():
    """Return a DataArray with a lon/lat grid and no time coordinate for use in tests."""
    data = np.linspace(300, 250, 3 * 4 * 4).reshape((3, 4, 4))
    ds = xr.Dataset(
        {'temperature': (['isobaric', 'lat', 'lon'], data)},
        coords={
            'isobaric': xr.DataArray(
                np.array([850., 700., 500.]),
                name='isobaric',
                dims=['isobaric'],
                attrs={'units': 'hPa'}
            ),
            'lat': xr.DataArray(
                np.linspace(30, 40, 4),
                name='lat',
                dims=['lat'],
                attrs={'units': 'degrees_north'}
            ),
            'lon': xr.DataArray(
                np.linspace(260, 270, 4),
                name='lon',
                dims=['lon'],
                attrs={'units': 'degrees_east'}
            )
        }
    )
    ds['temperature'].attrs['units'] = 'kelvin'

    return ds.metpy.parse_cf('temperature')


@pytest.fixture()
def test_da_xy():
    """Return a DataArray with a x/y grid and a time coordinate for use in tests."""
    data = np.linspace(300, 250, 3 * 3 * 4 * 4).reshape((3, 3, 4, 4))
    ds = xr.Dataset(
        {'temperature': (['time', 'isobaric', 'y', 'x'], data),
         'lambert_conformal': ([], '')},
        coords={
            'time': xr.DataArray(
                np.array([np.datetime64('2018-07-01T00:00'),
                          np.datetime64('2018-07-01T06:00'),
                          np.datetime64('2018-07-01T12:00')]),
                name='time',
                dims=['time']
            ),
            'isobaric': xr.DataArray(
                np.array([850., 700., 500.]),
                name='isobaric',
                dims=['isobaric'],
                attrs={'units': 'hPa'}
            ),
            'y': xr.DataArray(
                np.linspace(-1000, 500, 4),
                name='y',
                dims=['y'],
                attrs={'units': 'km'}
            ),
            'x': xr.DataArray(
                np.linspace(0, 1500, 4),
                name='x',
                dims=['x'],
                attrs={'units': 'km'}
            )
        }
    )
    ds['temperature'].attrs = {
        'units': 'kelvin',
        'grid_mapping': 'lambert_conformal'
    }
    ds['lambert_conformal'].attrs = {
        'grid_mapping_name': 'lambert_conformal_conic',
        'standard_parallel': 50.0,
        'longitude_of_central_meridian': -107.0,
        'latitude_of_projection_origin': 50.0,
        'earth_shape': 'spherical',
        'earth_radius': 6367470.21484375
    }

    return ds.metpy.parse_cf('temperature')


def test_grid_deltas_from_dataarray_lonlat(test_da_lonlat):
    """Test grid_deltas_from_dataarray with a lonlat grid."""
    dx, dy = grid_deltas_from_dataarray(test_da_lonlat)
    true_dx = np.array([[[321609.59212064, 321609.59212065, 321609.59212064],
                         [310320.85961483, 310320.85961483, 310320.85961483],
                         [297980.72966733, 297980.72966733, 297980.72966733],
                         [284629.6008561, 284629.6008561, 284629.6008561]]]) * units.m
    true_dy = np.array([[[369603.78775948, 369603.78775948, 369603.78775948, 369603.78775948],
                         [369802.28173967, 369802.28173967, 369802.28173967, 369802.28173967],
                         [370009.56291098, 370009.56291098, 370009.56291098,
                          370009.56291098]]]) * units.m
    assert_array_almost_equal(dx, true_dx, 5)
    assert_array_almost_equal(dy, true_dy, 5)


def test_grid_deltas_from_dataarray_xy(test_da_xy):
    """Test grid_deltas_from_dataarray with a xy grid."""
    dx, dy = grid_deltas_from_dataarray(test_da_xy)
    true_dx = np.array([[[[500] * 3]]]) * units('km')
    true_dy = np.array([[[[500]] * 3]]) * units('km')
    assert_array_almost_equal(dx, true_dx, 5)
    assert_array_almost_equal(dy, true_dy, 5)


def test_first_derivative_xarray_lonlat(test_da_lonlat):
    """Test first derivative with an xarray.DataArray on a lonlat grid in each axis usage."""
    deriv = first_derivative(test_da_lonlat, axis='lon')  # dimension coordinate name
    deriv_alt1 = first_derivative(test_da_lonlat, axis='x')  # axis type
    deriv_alt2 = first_derivative(test_da_lonlat, axis=-1)  # axis number

    # Build the xarray of the desired values
    partial = xr.DataArray(
        np.array([-3.30782978e-06, -3.42816074e-06, -3.57012948e-06, -3.73759364e-06]),
        coords=(('lat', test_da_lonlat['lat']),)
    )
    _, truth = xr.broadcast(test_da_lonlat, partial)
    truth.coords['crs'] = test_da_lonlat['crs']
    truth.attrs['units'] = 'kelvin / meter'

    # Assert result matches expectation
    xr.testing.assert_allclose(deriv, truth)
    assert deriv.metpy.units == truth.metpy.units

    # Assert alternative specifications give same result
    xr.testing.assert_identical(deriv_alt1, deriv)
    xr.testing.assert_identical(deriv_alt2, deriv)


def test_first_derivative_xarray_time_and_default_axis(test_da_xy):
    """Test first derivative with an xarray.DataArray over time as default first dimension."""
    deriv = first_derivative(test_da_xy)
    truth = xr.full_like(test_da_xy, -0.000777000777)
    truth.attrs['units'] = 'kelvin / second'

    xr.testing.assert_allclose(deriv, truth)
    assert deriv.metpy.units == truth.metpy.units


def test_second_derivative_xarray_lonlat(test_da_lonlat):
    """Test second derivative with an xarray.DataArray on a lonlat grid."""
    deriv = second_derivative(test_da_lonlat, axis='lat')

    # Build the xarray of the desired values
    partial = xr.DataArray(
        np.array([1.67155420e-14, 1.67155420e-14, 1.74268211e-14, 1.74268211e-14]),
        coords=(('lat', test_da_lonlat['lat']),)
    )
    _, truth = xr.broadcast(test_da_lonlat, partial)
    truth.coords['crs'] = test_da_lonlat['crs']
    truth.attrs['units'] = 'kelvin / meter^2'

    xr.testing.assert_allclose(deriv, truth)
    assert deriv.metpy.units == truth.metpy.units


def test_gradient_xarray(test_da_xy):
    """Test the 3D gradient calculation with a 4D DataArray in each axis usage."""
    deriv_x, deriv_y, deriv_p = gradient(test_da_xy, axes=('x', 'y', 'isobaric'))
    deriv_x_alt1, deriv_y_alt1, deriv_p_alt1 = gradient(test_da_xy,
                                                        axes=('x', 'y', 'vertical'))
    deriv_x_alt2, deriv_y_alt2, deriv_p_alt2 = gradient(test_da_xy, axes=(3, 2, 1))

    truth_x = xr.full_like(test_da_xy, -6.993007e-07)
    truth_x.attrs['units'] = 'kelvin / meter'

    truth_y = xr.full_like(test_da_xy, -2.797203e-06)
    truth_y.attrs['units'] = 'kelvin / meter'

    partial = xr.DataArray(
        np.array([0.04129204, 0.03330003, 0.02264402]),
        coords=(('isobaric', test_da_xy['isobaric']),)
    )
    _, truth_p = xr.broadcast(test_da_xy, partial)
    truth_p.coords['crs'] = test_da_xy['crs']
    truth_p.attrs['units'] = 'kelvin / hectopascal'

    # Assert results match expectations
    xr.testing.assert_allclose(deriv_x, truth_x)
    assert deriv_x.metpy.units == truth_x.metpy.units
    xr.testing.assert_allclose(deriv_y, truth_y)
    assert deriv_y.metpy.units == truth_y.metpy.units
    xr.testing.assert_allclose(deriv_p, truth_p)
    assert deriv_p.metpy.units == truth_p.metpy.units

    # Assert alternative specifications give same results (up to attribute differences)
    xr.testing.assert_equal(deriv_x_alt1, deriv_x)
    xr.testing.assert_equal(deriv_y_alt1, deriv_y)
    xr.testing.assert_equal(deriv_p_alt1, deriv_p)
    xr.testing.assert_equal(deriv_x_alt2, deriv_x)
    xr.testing.assert_equal(deriv_y_alt2, deriv_y)
    xr.testing.assert_equal(deriv_p_alt2, deriv_p)


def test_gradient_xarray_implicit_axes(test_da_xy):
    """Test the 2D gradient calculation with a 2D DataArray and no axes specified."""
    data = test_da_xy.isel(time=0, isobaric=2)
    deriv_y, deriv_x = gradient(data)

    truth_x = xr.full_like(data, -6.993007e-07)
    truth_x.attrs['units'] = 'kelvin / meter'

    truth_y = xr.full_like(data, -2.797203e-06)
    truth_y.attrs['units'] = 'kelvin / meter'

    xr.testing.assert_allclose(deriv_x, truth_x)
    assert deriv_x.metpy.units == truth_x.metpy.units

    xr.testing.assert_allclose(deriv_y, truth_y)
    assert deriv_y.metpy.units == truth_y.metpy.units


def test_laplacian_xarray_lonlat(test_da_lonlat):
    """Test laplacian with an xarray.DataArray on a lonlat grid."""
    laplac = laplacian(test_da_lonlat, axes=('lat', 'lon'))

    # Build the xarray of the desired values
    partial = xr.DataArray(
        np.array([1.67155420e-14, 1.67155420e-14, 1.74268211e-14, 1.74268211e-14]),
        coords=(('lat', test_da_lonlat['lat']),)
    )
    _, truth = xr.broadcast(test_da_lonlat, partial)
    truth.coords['crs'] = test_da_lonlat['crs']
    truth.attrs['units'] = 'kelvin / meter^2'

    xr.testing.assert_allclose(laplac, truth)
    assert laplac.metpy.units == truth.metpy.units


def test_first_derivative_xarray_pint_conversion(test_da_lonlat):
    """Test first derivative with implicit xarray to pint quantity conversion."""
    dx, _ = grid_deltas_from_dataarray(test_da_lonlat)
    deriv = first_derivative(test_da_lonlat, delta=dx, axis=-1)
    truth = np.array([[[-3.30782978e-06] * 4, [-3.42816074e-06] * 4, [-3.57012948e-06] * 4,
                       [-3.73759364e-06] * 4]] * 3) * units('kelvin / meter')
    assert_array_almost_equal(deriv, truth, 12)


def test_gradient_xarray_pint_conversion(test_da_xy):
    """Test the 2D gradient calculation with a 2D DataArray and implicit pint conversion."""
    data = test_da_xy.isel(time=0, isobaric=2)
    deriv_y, deriv_x = gradient(data, coordinates=(data.metpy.y, data.metpy.x))

    truth_x = np.ones_like(data) * -6.993007e-07 * units('kelvin / meter')
    truth_y = np.ones_like(data) * -2.797203e-06 * units('kelvin / meter')

    assert_array_almost_equal(deriv_x, truth_x, 12)
    assert_array_almost_equal(deriv_y, truth_y, 12)
