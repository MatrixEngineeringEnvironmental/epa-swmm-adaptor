# -*- coding: utf-8 -*-
import pytest
import os
import pandas as pd
import datetime
import xml.etree.ElementTree as ET
import filecmp
import shutil
from frozendict import frozendict
from pathlib import Path
import xarray as xr
import logging

from epaswmmadaptor.epaswmm import add_attributes
from epaswmmadaptor.epaswmm import read_run_info
from epaswmmadaptor.epaswmm import file_element
from epaswmmadaptor.epaswmm import time_element
from epaswmmadaptor.epaswmm import read_netcdf
from epaswmmadaptor.epaswmm import bytes_to_string
from epaswmmadaptor.epaswmm import write_runfile
from epaswmmadaptor.epaswmm import make_df
from epaswmmadaptor.epaswmm import write_rainfall
from epaswmmadaptor.epaswmm import read_units
from epaswmmadaptor.epaswmm import read_rpt_file
from epaswmmadaptor.epaswmm import read_errors_warnings
from epaswmmadaptor.epaswmm import write_run_diagnostics
from epaswmmadaptor.epaswmm import read_rating_curve
from epaswmmadaptor.epaswmm import read_control_rules
from epaswmmadaptor.epaswmm import dir_element
from epaswmmadaptor.epaswmm import create_xarray_dataset
from epaswmmadaptor.epaswmm import setup_logger
from epaswmmadaptor.epaswmm import write_netcdf

os.chdir(os.getcwd() + "//tests//module_adapter//Don")
print(os.getcwd())

__author__ = "lboutin"
__copyright__ = "lboutin"
__license__ = "mit"

logger_filename = "test_adapter.log"
main_logger = setup_logger('EPASWMM FEWS Python Logger', logger_filename, logging.INFO)


def setup_logger(name, log_file, logging_level=logging.INFO):
    """To setup as many loggers as you want"""
    formatter = logging.Formatter('%(levelname)s: External Adapter - %(message)s (%(asctime)s)')
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    return logger


def test_bytes_to_string():
    df = pd.DataFrame({'col1': [31, 30], 'col2': [b'Jan', b'Apr'], 'col3': [b'yes', b'maybe']})
    df = bytes_to_string(df, col_to_convert=['col2', 'col3'])
    assert (df['col2'] == ['Jan', 'Apr']).all()


def test_dir_element():
    print(os.getcwd())
    path = dir_element(os.getcwd())
    elem = dir_element(ET.fromstring("<DummyXMLElement>" + os.getcwd() + "</DummyXMLElement>"))
    assert elem == Path(os.getcwd())
    assert path == Path(os.getcwd())


def test_file_element():
    print(os.getcwd())
    path = file_element(os.getcwd() + '\\input\\rain.nc')
    elem = file_element(ET.fromstring("<DummyXMLElement>" + os.getcwd() + "\\input\\rain.nc</DummyXMLElement>"))
    assert elem == Path(os.getcwd() + '\\input\\rain.nc')
    assert path == Path(os.getcwd() + '\\input\\rain.nc')


def test_time_element():
    date = {"date": '2000-01-25', "time": '12:46:33'}
    date_parsed = time_element(date)
    assert type(date_parsed) is datetime.datetime
    assert date_parsed.year == 2000
    assert date_parsed.month == 1
    assert date_parsed.day == 25
    assert date_parsed.hour == 12
    assert date_parsed.minute == 46
    assert date_parsed.second == 33


def test_read_run_info():
    # logger_filename = "test_adapter.log"
    # main_logger = setup_logger('EPASWMM FEWS Python Logger', logger_filename, logging.INFO)
    run_info = read_run_info(os.getcwd() + '//run_info.xml')
    assert run_info["netcdf"] == Path(".//input//rain.nc")
    assert run_info["diagnostic_xml"] == Path(".//log//run_diagnostics.xml")
    assert run_info["properties"]["model-executable"] == Path(str(Path(os.getcwd()).parents[0])+"//bin//swmm5.exe")
    assert run_info["properties"]["swmm_input_file"] == Path(".//model//DonRiver.inp")
    assert run_info["time_zone"] == -5
    assert type(run_info["time_zone"]) == float  # using float and not int because of potential for half timezones

    assert type(run_info["start_time"]) == pd.Timestamp
    assert run_info["start_time"].year == 2020
    assert run_info["start_time"].month == 3
    assert run_info["start_time"].day == 18
    assert run_info["start_time"].hour == 20
    assert run_info["start_time"].minute == 00

    assert type(run_info["end_time"]) == pd.Timestamp
    assert run_info["end_time"].year == 2020
    assert run_info["end_time"].month == 3
    assert run_info["end_time"].day == 19
    assert run_info["end_time"].hour == 20
    assert run_info["end_time"].minute == 00

    assert type(run_info["time0"]) == pd.Timestamp
    assert run_info["time0"].year == 2020
    assert run_info["time0"].month == 3
    assert run_info["time0"].day == 19
    assert run_info["time0"].hour == 20
    assert run_info["time0"].minute == 00

    assert type(run_info["last_obs_time"]) == pd.Timestamp
    assert run_info["last_obs_time"].year == 2020
    assert run_info["last_obs_time"].month == 3
    assert run_info["last_obs_time"].day == 19
    assert run_info["last_obs_time"].hour == 20
    assert run_info["last_obs_time"].minute == 00
    print("=====================================================================================================")
    print(run_info["properties"]["swmm_input_file"])

    assert run_info["properties"]["UDUNITS"] == Path(os.getcwd() + "//model//UDUNITS_lookup.csv")
    assert run_info["properties"]["out_nodes_netcdf"] == Path(os.getcwd() + "//output//DonRiver_output_nodes.nc")
    assert run_info["properties"]["out_links_netcdf"] == Path(os.getcwd() + "//output//DonRiver_output_links.nc")

    run_info_no_dams = read_run_info(os.getcwd() + '\\run_info_withoutDamRatingCurve.xml')
    assert "dam_rating_curve" not in run_info_no_dams

def test_read_netcdf():
    df = read_netcdf(os.getcwd() + '\\input\\rain.nc', col_to_convert=['station_id', 'station_names'])
    assert type(df) == pd.DataFrame
    assert (df.columns == pd.Index(['lat', 'lon', 'y', 'x', 'z', 'station_id', 'station_names', 'P'])).all()
    assert df.index.names == ['analysis_time', 'stations', 'time']
    assert type(df["station_id"][0]) == str
    assert type(df["station_names"][0]) == str
    assert df["station_id"].unique().tolist() == ['DON_1', 'DON_2', 'DON_3', 'DON_4', 'DON_6', 'DON_7', 'DON_9',
                                                  'DON_10', 'DON_11', 'DON_5', 'DON_8']
    assert df["station_names"].unique().tolist() == ['DON_1', 'DON_2', 'DON_3', 'DON_4', 'DON_6', 'DON_7', 'DON_9',
                                                     'DON_10', 'DON_11', 'DON_5', 'DON_8']
    assert type(df.reset_index()['time'][0]) == pd.Timestamp
    assert df.index.names == ['analysis_time', 'stations', 'time']
    assert df['P'].max() == 1.5
    assert df['P'].min() == 1.5
    assert df.ndim == 2
    assert df.shape == (275, 8)


def test_read_rating_curve():
    print(os.getcwd())
    file = os.getcwd() + "\\input\\Dam_rating_curve.xml"
    assert os.path.exists(file)
    rc_dict = read_rating_curve(file)
    assert list(rc_dict.keys())[0] == "LocationX"
    assert type(list(rc_dict.values())[0]) == str
    assert list(rc_dict.values())[
               0] == "LocationX     Rating     1     0\nLocationX               2     0\nLocationX               3     10\nLocationX               4     15\nLocationX               5     20\nLocationX               6     40\n"


def test_read_control_rules():
    #EQUIDISTANT Time Series (does NOT have has missing values)

    print(os.getcwd())
    file = os.getcwd() + "\\input\\Control_rules.xml"
    assert os.path.exists(file)
    dict = read_control_rules(file)
    assert len(dict) ==2
    assert list(dict.keys())[0] == "OL341-OUTLET"
    assert type(list(dict.values())[0]) == str
    assert list(dict.values())[0] == 'Rule AdapterRule1.1\nIF SIMULATION DATE = 03/18/2020\nAND SIMULATION CLOCKTIME = 22:00:00\nTHEN OUTLET OL341 SETTING = 0.1\n\n' \
                                     'Rule AdapterRule1.2\nIF SIMULATION DATE = 03/18/2020\nAND SIMULATION CLOCKTIME = 23:00:00\nTHEN OUTLET OL341 SETTING = 0.2\n\n' \
                                     'Rule AdapterRule1.3\nIF SIMULATION DATE = 03/19/2020\nAND SIMULATION CLOCKTIME = 05:00:00\nTHEN OUTLET OL341 SETTING = 0.3\n\n' \
                                     'Rule AdapterRule1.4\nIF SIMULATION DATE = 03/19/2020\nAND SIMULATION CLOCKTIME = 08:00:00\nTHEN OUTLET OL341 SETTING = 0.8\n\n'

    assert list(dict.values())[1] == 'Rule AdapterRule2.1\nIF SIMULATION DATE = 03/18/2020\nAND SIMULATION CLOCKTIME = 22:00:00\nTHEN OUTLET OL342 SETTING = 0.2\n\n' \
                                     'Rule AdapterRule2.2\nIF SIMULATION DATE = 03/18/2020\nAND SIMULATION CLOCKTIME = 23:00:00\nTHEN OUTLET OL342 SETTING = 0.4\n\n' \
                                     'Rule AdapterRule2.3\nIF SIMULATION DATE = 03/19/2020\nAND SIMULATION CLOCKTIME = 05:00:00\nTHEN OUTLET OL342 SETTING = 0.6\n\n' \
                                     'Rule AdapterRule2.4\nIF SIMULATION DATE = 03/19/2020\nAND SIMULATION CLOCKTIME = 08:00:00\nTHEN OUTLET OL342 SETTING = 0.9\n\n'


    #NON-EQUIDISTANT Time Series (has missing values)
    file = os.getcwd() + "\\input\\Control_rules_missing_values.xml"
    assert os.path.exists(file)
    dict = read_control_rules(file)
    assert len(dict) == 1
    assert list(dict.keys())[0] == "OL341-OUTLET"
    assert type(list(dict.values())[0]) == str
    assert list(dict.values())[
               0] == 'Rule AdapterRule1.1\nIF SIMULATION DATE = 04/23/2020\nAND SIMULATION CLOCKTIME = 18:00:00\nTHEN OUTLET OL341 SETTING = 0.5\n\n' \
                     'Rule AdapterRule1.2\nIF SIMULATION DATE = 04/24/2020\nAND SIMULATION CLOCKTIME = 05:00:00\nTHEN OUTLET OL341 SETTING = 0.4\n\n' \
                     'Rule AdapterRule1.3\nIF SIMULATION DATE = 04/24/2020\nAND SIMULATION CLOCKTIME = 18:00:00\nTHEN OUTLET OL341 SETTING = 0.3\n\n' \
                     'Rule AdapterRule1.4\nIF SIMULATION DATE = 04/24/2020\nAND SIMULATION CLOCKTIME = 23:00:00\nTHEN OUTLET OL341 SETTING = 0.2\n\n'

def test_write_rainfall():
    write_rainfall(os.getcwd() + '\\input\\rain.nc', os.getcwd() + '\\model\\DonRiver_rainfall.dat',
                   col_to_convert=['station_id', 'station_names'])
    assert os.path.exists(os.getcwd() + '\\model\\DonRiver_rainfall.dat')
    # compare the result of the method to the expected contents of the INP file.
    check_file_contents = filecmp.cmp(os.getcwd() + '\\model\\DonRiver_rainfall.dat',
                                      os.getcwd() + '\\model\\DonRiver_rainfall_expected.dat')
    assert check_file_contents


def test_write_runfile():
    run_info = read_run_info((os.getcwd() + '\\run_info.xml'))
    run_info["properties"]["swmm_input_file"] = os.getcwd() + "//model//standard.inp"
    run_info["properties"]["swmm_output_file"] = os.getcwd() + "//model//standard.rpt"
    shutil.copy(os.getcwd() + "//model//DonRiver_SOURCE TEST FILE.inp",
                run_info["properties"]["swmm_input_file"])

    rc_dict = read_rating_curve(run_info["dam_rating_curve"])
    rule_dict = read_control_rules(run_info["control_rule"])
    write_runfile(run_info, rc_dict,rule_dict)
    check_file_exists = os.path.exists(run_info["properties"]["swmm_input_file"])
    check_file_contents = filecmp.cmp(run_info["properties"]["swmm_input_file"],
                                      # compare the result of the method to the expected contents of the INP file.
                                      os.getcwd() + '\\model\\DonRiver_expected.inp')
    assert check_file_exists
    assert check_file_contents
    # ONE CURVE
    # Expecting that only LocationX Rating Curve Changed
    run_info["properties"]["swmm_input_file"] = os.getcwd() + "//model//1curve.inp"
    run_info["properties"]["swmm_output_file"] = os.getcwd() + "//model//1curve.rpt"
    shutil.copy(os.getcwd() + "//model//DonRiver_SOURCE TEST FILE.inp",
                run_info["properties"]["swmm_input_file"])
    rc_dict = read_rating_curve(os.getcwd() + '\\input\\Dam_rating_curve_1curve.xml')
    write_runfile(run_info, rc_dict, rule_dict)
    with open(run_info["properties"]["swmm_input_file"], 'r') as f:
        lines = f.readlines()
    assert lines[203].strip() == "LocationX     Rating     1     0"
    assert lines[208].strip() == "LocationX               6     40"
    assert lines[211].strip() == "LOC_Y     Rating     101     888"
    assert lines[216].strip() == "LOC_Y               106     888"
    assert lines[220].strip() == "LOC_Z               Rating    101          777"
    assert lines[225].strip() == "LOC_Z                          106         777"
    assert lines[238].strip() == "LocationX     Storage     100     999"
    assert lines[243].strip() == "LocationX               600     999"
    assert len(lines) == 347

    # TWO CURVES
    # Expecting that LOC_Y and  LocationX Rating Curve Changed
    run_info["properties"]["swmm_input_file"] = os.getcwd() + "//model//2curve.inp"
    run_info["properties"]["swmm_output_file"] = os.getcwd() + "//model//2curve.rpt"
    shutil.copy(os.getcwd() + "//model//DonRiver_SOURCE TEST FILE.inp",
                run_info["properties"]["swmm_input_file"])
    rc_dict = read_rating_curve(os.getcwd() + '\\input\\Dam_rating_curve_2curve.xml')
    write_runfile(run_info, rc_dict, rule_dict)
    with open(run_info["properties"]["swmm_input_file"], 'r') as f:
        lines = f.readlines()
    assert lines[203].strip() == "LocationX     Rating     1     0"
    assert lines[208].strip() == "LocationX               6     40"
    assert lines[211].strip() == "LOC_Y     Rating     2     1.1"
    assert lines[216].strip() == "LOC_Y               10     1.9"
    assert lines[220].strip() == "LOC_Z               Rating    101          777"
    assert lines[225].strip() == "LOC_Z                          106         777"
    assert lines[238].strip() == "LocationX     Storage     100     999"
    assert lines[243].strip() == "LocationX               600     999"
    assert len(lines) == 347


    with pytest.raises(SystemExit):
        read_rating_curve(os.getcwd() + '\\input\\Dam_rating_curve_curveDuplicate.xml')

    with pytest.raises(SystemExit):
        read_rating_curve(os.getcwd() + '\\input\\Dam_rating_curve_0curves.xml')

def test_create_xarray_dataset():
    run_info = read_run_info(os.getcwd() + '//run_info.xml')
    data_dict = read_rpt_file(run_info["properties"]["swmm_output_file"])
    swmm_unit_dict = read_units(run_info["properties"]["UDUNITS"])
    combined_ds_nodes, combined_ds_links = create_xarray_dataset(data_dict, swmm_unit_dict)
    assert combined_ds_nodes.sizes == frozendict({'time': 94, 'station_id': 6})  # 6 nodes
    assert combined_ds_links.sizes == frozendict({'time': 94, 'station_id': 5})  # 5 links
    assert type(combined_ds_nodes) is not None
    assert type(combined_ds_links) is not None
    assert type(combined_ds_nodes) == xr.Dataset
    assert type(combined_ds_links) == xr.Dataset


def test_add_attributes():
    """
    1) Check to make sure it returns an Error if ds.time and ds.station_id NOT existing
    """
    run_info = read_run_info(os.getcwd() + '//run_info.xml')
    data_dict = read_rpt_file(run_info["properties"]["swmm_output_file"])
    swmm_unit_dict = read_units(run_info["properties"]["UDUNITS"])
    ds, _ = create_xarray_dataset(data_dict, swmm_unit_dict)
    assert (list(ds.attrs) == ['Conventions', 'title', 'institution', 'source', 'history', 'references',
                               'Metadata_Conventions', 'summary', 'date_created', 'coordinate_system', 'featureType',
                               'comment'])
    assert ds.attrs["Conventions"] == "CF-1.6"
    assert ds.attrs["title"] == "Data from simulation outputs"
    assert ds.attrs["institution"] == "TRCA"
    assert ds.attrs["source"] == "Don River Hydrology Update Project Number 60528844 December 2018"
    assert ds.attrs["references"] == "https://trca.ca/"
    assert ds.attrs["Metadata_Conventions"] == "Unidata Dataset Discovery v1.0"
    assert ds.attrs["summary"] == "EPA SWMM simulation output"
    assert "EMT" in ds.attrs["date_created"]
    assert ds.attrs["coordinate_system"] == "WGS 1984"
    assert ds.attrs["featureType"] == "timeSeries"
    assert ds.attrs["comment"] == "created from Python script EPA-SWMM-Adaptor"
    assert list(ds.coords) == ["time", "station_id"]


def test_make_df():
    """
    1) Check to make sure it returns an Error if ds.time and ds.station_id NOT existing
    """
    print(os.getcwd())
    file = os.getcwd() + "\\model\\test_make_df.csv"
    with open(file) as f:
        lines = f.readlines()
    start = 5
    nrows = 8
    df_header = ['Date', 'Time', 'Flow', 'Velocity', 'Depth', 'Capacity']
    df = make_df(lines, start, nrows, df_header)
    assert isinstance(df.iloc[3]['Flow'], float)
    assert isinstance(df.iloc[3]['Velocity'], float)
    assert isinstance(df.iloc[3]['Depth'], float)
    assert isinstance(df.iloc[3]['Capacity'], float)

    assert df.iloc[3]['Flow'] == pytest.approx(0.004)
    assert df.iloc[3]['Velocity'] == pytest.approx(0.0, 0.0001)
    assert df.iloc[3]['Depth'] == pytest.approx(0.027, 0.0001)
    assert df.iloc[3]['Capacity'] == 1.000
    assert (df.columns == ['Flow', 'Velocity', 'Depth', 'Capacity']).all()

    print(os.getcwd())
    file = os.getcwd() + "\\model\\test_make_df2.csv"
    with open(file) as f:
        lines = f.readlines()
    start = 5
    nrows = 8
    df_header = ['Date', 'Time', 'Inflow', 'Flooding', 'Depth', 'Head']
    df = make_df(lines, start, nrows, df_header)
    assert df.iloc[3]['Inflow'] == 0.000
    assert df.iloc[3]['Flooding'] == 0.000
    assert df.iloc[3]['Depth'] == 0.000
    assert df.iloc[3]['Head'] == pytest.approx(239.350, 0.001)
    assert (df.columns == ['Inflow', 'Flooding', 'Depth', 'Head']).all()


def test_read_units():
    """
    Check if reading in the units lookup and attributes information properly.
    """
    run_info_file = Path(os.getcwd() + "\\run_info.xml")
    print("======================" + str(run_info_file))
    global run_info
    run_info = read_run_info(run_info_file)
    file = os.getcwd() + "\\UDUNITS_lookup.csv"
    dict_units = read_units(file)
    assert dict_units['Setting'] == {'UDUNITS': 'na', 'long_name': 'not_available', 'standard_name': 'not_available'}
    assert list(dict_units['Setting'].keys()) == ['UDUNITS', 'long_name', 'standard_name']

    with pytest.raises(SystemExit):
        file = os.getcwd() + "\\UDUNITS_lookup_BAD.csv"
        read_units(file)


def test_read_rpt_file():
    """
    Test reading the results *.rpt file ASCII format to extract timeSeries of EPASWMM.
    """
    # Working file
    file1 = os.getcwd() + "\\model\\FEWS_Test_model_output.rpt"
    file2 = os.getcwd() + "\\model\\FEWS_Test_model_output2.rpt"

    data_dict = read_rpt_file(file1)
    print(data_dict.keys())
    expected_list = ['Link_C1', 'Link_C2', 'Link_C3', 'Link_C4', 'Node_J1',
                     'Node_J2', 'Node_J3', 'Node_J4', 'Node_Out1',
                     'Subcatchment_DON_1', 'Subcatchment_DON_10', 'Subcatchment_DON_11', 'Subcatchment_DON_2',
                     'Subcatchment_DON_3',
                     'Subcatchment_DON_4', 'Subcatchment_DON_5', 'Subcatchment_DON_6', 'Subcatchment_DON_7',
                     'Subcatchment_DON_8', 'Subcatchment_DON_9']
    assert sorted(data_dict.keys()) == expected_list
    expected_list = ['Data', 'Header', 'Units', 'df_header', 'end_line', 'start_line', 'units_dict']
    assert sorted(data_dict['Node_J2']) == expected_list
    expected_list = ['Depth', 'Flooding', 'Head', 'Inflow']
    assert sorted(data_dict['Node_J2']['Header']) == expected_list
    expected_list = ['CFS', 'CFS', 'feet', 'feet']
    assert sorted(data_dict['Node_J2']['Units']) == expected_list
    expected_list = ['Date', 'Depth', 'Flooding', 'Head', 'Inflow', 'Time']
    assert sorted(data_dict['Node_J2']['df_header']) == expected_list
    assert data_dict['Node_J2']['end_line'] == 1673
    assert data_dict['Node_J2']['start_line'] == 1576
    expected_list = ['Depth', 'Flooding', 'Head', 'Inflow']
    assert sorted(data_dict['Node_J2']['units_dict']) == expected_list

    data_dict = read_rpt_file(file2)
    print(data_dict.keys())
    expected_list = ['Link_OL27', 'Link_OL27.1', 'Link_OL271', 'Link_OL271.1',
                     'Link_OL271.3', 'Link_OL271.4', 'Link_OL271.5', 'Link_OL291', 'Link_OL30001',
                     'Link_OL303', 'Link_OL303.1', 'Link_OL304', 'Link_OL315', 'Link_OL341',
                     'Link_OL341.1', 'Link_OL341.2', 'Link_OL348', 'Link_OL348.1',
                     'Link_OL348.2', 'Link_OL348.3', 'Link_OL348.4', 'Link_OL348.5',
                     'Link_OL348.6', 'Link_OL348.7', 'Link_OL348.8', 'Link_OL349',
                     'Link_OL349.1', 'Link_OL349.2', 'Link_OL349.3', 'Link_OL349.4',
                     'Link_OL349.5', 'Link_OL349.6', 'Link_OL349.7', 'Link_OL349.8',
                     'Link_OL349.9', 'Link_OL350.1', 'Link_OL350.2', 'Link_OL37', 'Link_OL4',
                     'Link_OL4.3', 'Link_OL4.4', 'Link_OL4.5', 'Link_OL404', 'Link_OL405',
                     'Link_OL406', 'Link_OL406.1', 'Link_OL50', 'Link_OL66', 'Link_OL79',
                     'Link_OL95', 'Node_J001', 'Node_J690', 'Node_J691', 'Node_J692',
                     'Node_J693', 'Node_J694', 'Node_J695', 'Node_J696', 'Node_J697',
                     'Node_J698', 'Node_J699', 'Node_J700', 'Node_J701', 'Node_J702',
                     'Node_J703', 'Node_J704']
    assert sorted(data_dict.keys()) == expected_list

    # Link information
    expected_list = ['Data', 'Header', 'Units', 'df_header', 'end_line', 'start_line', 'units_dict']
    assert sorted(data_dict['Link_OL95']) == expected_list
    expected_list = ['Capacity', 'Depth', 'Flow', 'Velocity']
    assert sorted(data_dict['Link_OL95']['Header']) == expected_list
    expected_list = ['CMS', 'Setting', 'm/sec', 'meters']
    assert sorted(data_dict['Link_OL95']['Units']) == expected_list
    expected_list = ['Capacity', 'Date', 'Depth', 'Flow', 'Time', 'Velocity']
    assert sorted(data_dict['Link_OL95']['df_header']) == expected_list
    assert data_dict['Link_OL95']['end_line'] == 89917
    assert data_dict['Link_OL95']['start_line'] == 89052
    expected_list = ['Capacity', 'Depth', 'Flow', 'Velocity']
    assert sorted(data_dict['Link_OL95']['units_dict']) == expected_list
    assert data_dict['Link_OL95']['Data']['Flow'].count() == 862
    print(data_dict['Link_OL95']['Data']['Flow'])
    assert data_dict['Link_OL95']['Data']['Flow'].iloc[-1] == pytest.approx(0.004, 0.001)

    # Node information
    expected_list = ['Data', 'Header', 'Units', 'df_header', 'end_line', 'start_line', 'units_dict']
    assert sorted(data_dict['Node_J001']) == expected_list
    expected_list = ['Depth', 'Flooding', 'Head', 'Inflow']
    assert sorted(data_dict['Node_J001']['Header']) == expected_list
    expected_list = ['CMS', 'CMS', 'meters', 'meters']
    assert sorted(data_dict['Node_J001']['Units']) == expected_list
    expected_list = ['Date', 'Depth', 'Flooding', 'Head', 'Inflow', 'Time']
    assert sorted(data_dict['Node_J001']['df_header']) == expected_list
    assert data_dict['Node_J001']['end_line'] == 33298
    assert data_dict['Node_J001']['start_line'] == 32433
    expected_list = ['Depth', 'Flooding', 'Head', 'Inflow']
    assert sorted(data_dict['Node_J001']['units_dict']) == expected_list
    assert data_dict['Node_J001']['Data']['Head'].count() == 862
    assert data_dict['Node_J001']['Data']['Head'].iloc[-1] == pytest.approx(291.763, 0.001)


def test_read_fail_rpt_file():
    """
    Test reading the results *.rpt file that should be failing.
    """
    # Error files
    file3 = os.getcwd() + "\\model\\FEWS_Test_model_output_exampleError.rpt"
    file4 = os.getcwd() + "\\model\\FEWS_Test_model_output_noTS.rpt"
    file5 = os.getcwd() + "\\model\\FEWS_Test_model_output_noTS2.rpt"

    with pytest.raises(SystemExit):
        read_rpt_file(file3)
    with pytest.raises(SystemExit):
        read_rpt_file(file4)
    with pytest.raises(SystemExit):
        read_rpt_file(file5)


def test_read_errors_warnings():
    file = os.getcwd() + "\\model\\FEWS_Test_model_output_exampleError.rpt"
    df = read_errors_warnings([file])
    assert df["level"][0] == 2
    assert df["description"][0] == "WARNING 03: negative offset ignored for Link C1"
    assert df["level"][4] == 1
    assert df["description"][4] == "ERROR 317: cannot open rainfall data file RAINFALL.DAT."

    file1 = os.getcwd() + "\\model\\FEWS_Test_model_output_exampleError.rpt"
    file2 = os.getcwd() + "\\log\\PythonLog_ExampleLog.txt"

    # CHECK reading of both Python log and
    df = read_errors_warnings([file1, file2])

    # TODO add test case
    assert df["level"][0] == 2
    assert df["description"][0] == "WARNING 03: negative offset ignored for Link C1"
    assert df["level"][4] == 1
    assert df["description"][4] == "ERROR 317: cannot open rainfall data file RAINFALL.DAT."
    assert df["level"][5] == 2
    assert "WARNING" in df["description"][5]
    assert df["level"][6] == 1
    assert "ERROR" in df["description"][6]

    file = os.getcwd() + "\\model\\FEWS_Test_model_output_noErrorsWarnings.rpt"
    df_no_err_warn = read_errors_warnings([file])
    assert len(df_no_err_warn) == 0


def test_write_run_diagnostics():
    """
    1) Remove both the Python log file and the Run Diagnostics
    2) Write fake test Python errors to the log
    3)
    """

    file = os.getcwd() + "\\log\\test_write_run_diagnostics_().xml"
    try:
        os.remove(file)
    except OSError:
        pass
    assert not os.path.exists(file)

    logfile_test = "log//PythonLog_test.txt"
    try:
        os.remove(logfile_test)  # delete the log file if it exists
    except OSError:
        pass
    assert not os.path.exists(logfile_test)
    test_case_logger = setup_logger('Test Case Logger', logfile_test)
    test_case_logger.warning(
        "TEST WARNING")  # for testing the writing of the run_diagnostics, need to ensure that these test python warnings/errors occur at the top of the file
    test_case_logger.error("TEST ERROR")
    test_case_logger.info("TEST INFO")
    test_case_logger.info("TEST DEBUG")
    assert os.path.exists(logfile_test)

    df = read_errors_warnings([logfile_test,
                               os.getcwd() + "\\model\\FEWS_Test_model_output_exampleError.rpt"])
    test_case_logger.debug(df.columns)
    write_run_diagnostics(df, file)

    # CHECK file exists
    assert os.path.exists(file)

    # CHECK contents
    f = open(file, "r")
    lines = f.readlines()
    # CHECK header
    assert lines[0] == '<?xml version="1.0" encoding="UTF-8"?>\n'
    assert lines[1] == '<Diag xmlns="http://www.wldelft.nl/fews/PI"\n'
    assert lines[2] == 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
    assert lines[
               3] == 'xsi:schemaLocation="http://www.wldelft.nl/fews/PI http://fews.wldelft.nl/schemas/version1.0/pi-schemas/pi_diag.xsd" version="1.2">\n'

    # CHECK sample of
    assert "TEST WARNING" in lines[4]  # Python errors have timestamp, so have to do a looser check
    assert "TEST ERROR" in lines[5]  # Python errors have timestamp, so have to do a looser check
    assert "TEST INFO" in lines[6]  # Python errors have timestamp, so have to do a looser check
    assert "TEST DEBUG" in lines[7]  # Python errors have timestamp, so have to do a looser check
    assert lines[8] == '            <line level="2" description="WARNING 03: negative offset ignored for Link C1"/>\n'
    assert lines[9] == '            <line level="2" description="WARNING 03: negative offset ignored for Link C2"/>\n'
    assert lines[10] == '            <line level="2" description="WARNING 03: negative offset ignored for Link C4"/>\n'
    assert lines[11] == '            <line level="2" description="WARNING 03: negative offset ignored for Link C3"/>\n'
    assert lines[
               12] == '            <line level="1" description="ERROR 317: cannot open rainfall data file RAINFALL.DAT."/>\n'
    assert lines[13] == '</Diag>'


def test_write_netcdf():
    assert os.path.exists(os.getcwd() + "\\output")
    run_info_file = Path(os.getcwd() + "\\run_info.xml")
    run_info = read_run_info(run_info_file)
    properties = run_info["properties"]
    swmm_unit_dict = read_units(properties["UDUNITS"])
    data_dict = read_rpt_file(properties["swmm_output_file"])
    combined_ds_nodes, combined_ds_links = create_xarray_dataset(data_dict, swmm_unit_dict)

    # CHECK Nodes NetCDF file is written
    file = properties["out_nodes_netcdf"]
    print("FILE = " + str(file))
    try:
        os.remove(file)
    except OSError:
        print("CAN'T REMOVE FILE = " + str(file))
    assert not os.path.exists(file)
    write_netcdf(combined_ds_nodes, properties["out_nodes_netcdf"])
    assert os.path.exists(file)

    # CHECK Links NetCDF file is written
    file = properties["out_links_netcdf"]
    try:
        os.remove(file)
    except OSError:
        pass
    assert not os.path.exists(file)
    write_netcdf(combined_ds_links, properties["out_links_netcdf"])
    assert os.path.exists(file)
