# -*- coding: utf-8 -*-
"""
This is the base file that can serve as a starting point for the Python Adaptor development. 

This file can also be used as template for Python modules.
main_logger.
"""
import argparse as ap
import csv
import datetime
import logging
import os
import pandas as pd
from pathlib import Path
import subprocess
import re
from shutil import move
import xarray as xr
import sys
import xml.etree.ElementTree as ET

# For package only #
# uncomment this when building the wheel distribution: python setup.py bdist_wheel
# from epaswmmadaptor import epaswmm
# from epaswmmadaptor import __version__

__author__ = "pbishop,lboutin"
__copyright__ = "pbishop,lboutin"
__license__ = "mit"

# XML namespace dict, needed to find elements
namespace = {"pi": "http://www.wldelft.nl/fews/PI"}


def add_attributes(ds):
    """
    Add model specific attributes to make it more CF compliant
    """
    ds.time.attrs["standard_name"] = "time"
    ds.time.attrs["long_name"] = "time"
    ds.time.attrs["axis"] = "T"

    ds.station_id.attrs["standard_name"] = "Station Identifier"
    ds.station_id.attrs["long_name"] = "EPA_SWMM Station Identifier"
    ds.station_id.attrs["axis"] = "XY"
    ds.station_id.attrs["cf_role"] = "timeseries_id"

    ds = ds.assign_attrs(
        Conventions="CF-1.6",
        title="Data from simulation outputs",
        institution="TRCA",
        source="Don River Hydrology Update Project Number 60528844 December 2018",
        history=datetime.datetime.utcnow().replace(microsecond=0).isoformat(" ")
        + " EMT: simulation results from EPA SWMM model",
        references="https://trca.ca/",
        Metadata_Conventions="Unidata Dataset Discovery v1.0",
        summary="EPA SWMM simulation output",
        date_created=datetime.datetime.utcnow().replace(microsecond=0).isoformat(" ")
        + " EMT",
        coordinate_system="WGS 1984",
        featureType="timeSeries",
        comment="created from Python script EPA-SWMM-Adaptor",
    )

    return ds


def bytes_to_string(df, col_to_convert):
    """
    Decodes columns in a dataframe. When the NetCDF file is read, string columns are encoded.
    """
    for x in col_to_convert:
        df[x] = df[x].str.decode('utf-8')
    return df


def check_properties(key, props, run_info_file):
    if key not in props:
        main_logger.error("Key (%s) was not specified in the run_info.xml file." % key)
        raise KeyError(
            f'"{key}" needs to be specified under <properties> in {run_info_file.resolve()}'
        )


def create_xarray_dataset(data_dict, swmm_unit_dict):
    """
    Creating xarray datasets.
    """
    main_logger.debug("Creating DataSet from the results DataFrame.")
    list_ds_nodes = []
    list_ds_links = []
    list_keys_ignored = []
    for key in data_dict.keys():
        try:
            header = data_dict[key]['Header']
            units = data_dict[key]['Units']
            rename_header = {}
        except Exception:
            main_logger.error("Failed to get header/units when creating dataset.")
            stop_program()

        for item in range(0, len(units)):
            try:
                rename_header[units[item]] = header[item]
                temp_df = data_dict[key]['Data'].copy(deep=True)
                temp_df = temp_df.rename(rename_header, axis='columns')
                temp_df['station_id'] = key
                temp_df.set_index(['station_id'], append=True, inplace=True)
                ds2 = xr.Dataset.from_dataframe(temp_df)
            except Exception:
                main_logger.error("Failed to create DataSet for {0}".format(temp_df['station_id']))
                stop_program()

        for var, unit in data_dict[key]['units_dict'].items():
            try:
                attributes_info = swmm_unit_dict.get(unit)
                for attrs, val in attributes_info.items():
                    if attrs == 'UDUNITS':
                        attrs = 'units'
                    ds2[var].attrs[attrs] = val
            except Exception:
                main_logger.error(
                    "Error raised due to EPA SWMM unit --> {0} is not recognized. Please add corresponding information into the UDUNITS_lookup.csv input file.".format(
                        unit))
                stop_program()
                raise KeyError(
                    "Error raised due to EPA SWMM unit --> {0} is not recognized. Please add corresponding information into the UDUNITS_lookup.csv input file.".format(
                        unit))

        try:
            if "node" in key.lower():
                list_ds_nodes.append(ds2)
            elif "link" in key.lower():
                list_ds_links.append(ds2)
            else:
                list_keys_ignored.append(key)
                pass
        except Exception:
            main_logger.error("Failed to append data to dataset for: {0}".format(key))
            stop_program()

    print("Locations ignored in the resulting output file (i.e. not a node or a link): \n\n" + str(list_keys_ignored))
    # Combining Dataset for each station_id with same type

    try:
        main_logger.debug("Start combining xarray DataSets for nodes ...")
        combined_ds_nodes = xr.combine_by_coords(list_ds_nodes)
        combined_ds_nodes = add_attributes(combined_ds_nodes)
    except Exception:
        main_logger.error("Failed to combining xarray DataSets for nodes")
        stop_program()

    try:
        main_logger.debug("Start combining xarray DataSets for links ...")
        combined_ds_links = xr.combine_by_coords(list_ds_links)
        combined_ds_links = add_attributes(combined_ds_links)
    except Exception:
        main_logger.error("Failed to combining xarray DataSets for links")
        stop_program()

    print("\nDone creating xarray DataSet for Nodes and Links.\n")
    main_logger.debug("Done creating xarray DataSet for Nodes and Links.")
    return combined_ds_nodes, combined_ds_links


def dir_element(elem, exists=True):
    """
    Checks if a string or XML element is a directory path, and returns the corresponding path.
    """
    if isinstance(elem, str):
        # such that this works if the path is in an attribute
        path = Path(elem)
    else:
        path = Path(elem.text)
    if exists and not path.is_dir():
        main_logger.error(
            "The following is expected to exist but was not found: %s" % (os.path.join(os.getcwd(), path)))
        stop_program()
        raise FileNotFoundError(path.resolve())
    return path


def file_element(elem, exists=True):
    """
    Checks if a string or XML element is a path, and returns the corresponding path.
    """
    if isinstance(elem, str):
        # such that this works if the path is in an attribute
        if "bin" in elem:
            path = Path(elem)
            root = Path(os.getcwd())
            path = os.path.join(root.parents[0], path)
            path = Path(path)
        else:
            path = Path(elem)
    else:
        path = Path(elem.text)

    if exists and not path.is_file():
        print("The following is expected to exist but was not found: %s" % (os.path.join(os.getcwd(), path)))
        main_logger.error(
            "The following is expected to exist but was not found: %s" % (os.path.join(os.getcwd(), path)))
        stop_program()
        raise FileNotFoundError(path.resolve())
    return path


def make_df(lines, start, nrows, df_header):
    """
    Method to create a pandas DataFrame from a subset of lines from the simulation results *.rpt file.
    """
    # PERFORMANCE ISSUE: parsers.py from pandas is causing lost in performance.
    #     Using pandas.DataFrame() method allowed increasing performance.
    # df = pd.read_csv(file, delimiter=r"\s+", names=df_header, header=None,
    # skiprows=start+2,nrows=nrows-1, parse_dates=[0], dayfirst = False)

    try:
        df = pd.DataFrame([[i for i in line.strip().split()] for line in lines[start + 2:start + nrows - 1]],
                          columns=df_header)
        df['DateO'] = pd.to_datetime(df['Date'])
        df['TimeO'] = pd.to_timedelta(df['Time'])
        df['time'] = df['DateO'] + df['TimeO']
        df = df.drop(columns=['DateO', 'TimeO', 'Date', 'Time'])
        df = df.set_index('time')
        df = df.apply(pd.to_numeric)
    except Exception:
        main_logger.error("Failed to create dataframe for line starting with: {0}".format(lines[start]))
        stop_program()
    return df


def read_netcdf(netcdf_filename, col_to_convert):
    """ 
    Read a netCDF file and return a pandas DataFrame
    """
    ds = xr.open_dataset(netcdf_filename)
    try:
        df = ds.to_dataframe()
    except Exception:
        main_logger.error("Failed to create dataframe when reading the NetCDF file.")
        stop_program()
    try:
        df = bytes_to_string(df, col_to_convert)
    except Exception:
        main_logger.error("Failed to decode following columns when reading NetCDF file: " + ','.join(col_to_convert))
        stop_program()
    return df


def read_errors_warnings(file_list):
    """
    Read errors and warnings from the *.rpt ASCII and Python log file output from the simulation.
    """
    main_logger.debug("File list: {0}".format(file_list))
    list_warning_error = []
    df = None

    for f in file_list:
        try:
            with open(f, "r") as fi:
                for ln in fi:
                    if any(x in ln for x in ["ERROR", "WARNING", "DEBUG", "INFO", "FATAL"]):
                        list_warning_error.append(ln.strip())

        except Exception:
            main_logger.error(
                "The following is expected to exist but was not found: {0}".format(os.path.join(os.getcwd(), f)))
            stop_program()
            raise FileNotFoundError(Path(f).resolve())

    if len(list_warning_error) > 0:
        df = pd.Series(list_warning_error).str.split(":", 1, expand=True).rename(
            columns={0: "level", 1: "description"})
        df["description"] = [x.strip() for x in df["description"]]
        df = df.drop_duplicates(["level",
                                 "description"]).reset_index()  # SWMM outputs identical warnings sometimes, which does not add any value
    else:
        df = None

    # CONVERT TO FEWS ERROR Numbering
    if df is not None and len(df) > 0:
        df['description'] = df['level'] + ": " + df['description']
        for index, row in df.iterrows():
            if "DEBUG" in row["level"]:
                df.at[index, "level"] = 4
            if "INFO" in row["level"]:
                df.at[index, "level"] = 3
            if "WARN" in row["level"]:
                df.at[index, "level"] = 2
            if "ERROR" in row["level"]:
                df.at[index, "level"] = 1
            if "FATAL" in row["level"]:
                df.at[index, "level"] = 0
    else:
        main_logger.info("No errors, warnings or info messages were detected.")
        df = pd.DataFrame(columns=['description', 'level'])
    return df


def read_rpt_file(rpt_input_file):
    """
    Read *.rpt ASCII file with timeSeries output from the simulation.
    """
    try:
        with open(rpt_input_file, "r") as f:
            lines = f.readlines()
            data_dict = {}
            in_data = False
            varchange = False
            old_name = ""
            main_logger.debug("Starting parsing *.rpt file...")
            # Parse ASCII *.rpt file into nested Dictionary/DataFrame
            for i in range(0, len(lines)):
                try:
                    if "<<<" in lines[i]:
                        new_name = lines[i].strip().strip("<<<").strip(">>>").lstrip(" ").rstrip(" ").replace(" ", "_")
                        print("Proceeding with --> ", new_name)
                        data_dict[new_name] = {'start_line': i + 3}

                        # Parsing Header and Units information.
                        # Two potential cases:
                        #   1) Date and Time located on the Header line (Nodes and Links)
                        #   2) Date and Time located on the Units line (Subcatchment)
                        header = lines[i + 2].strip().lstrip(" ").rstrip(" ").rstrip("/").split()
                        units = lines[i + 3].strip().lstrip(" ").rstrip(" ").rstrip("/").split()  # [2::]
                        if len(header) > len(units):
                            df_header = header
                            header = header[2::]
                        else:
                            df_header = units[:2] + header
                            units = units[2::]
                        units_dict = {}

                        for item in range(len(header)):
                            units_dict[header[item]] = units[item]
                        data_dict[new_name] = {'start_line': i + 3, 'Header': header, 'Units': units,
                                               'df_header': df_header, 'units_dict': units_dict}

                        if not in_data:
                            in_data = True

                        elif varchange:
                            varchange = False
                            # Pass when there's a change in variable
                        else:
                            data_dict[old_name]['end_line'] = i - 3
                            df_header = data_dict[old_name]['df_header']
                            start = data_dict[old_name]['start_line']
                            nrows = data_dict[old_name]['end_line'] - data_dict[old_name]['start_line']
                            df = make_df(lines, start, nrows, df_header)
                            data_dict[old_name]['Data'] = df

                    elif not in_data:
                        pass
                    elif "***" in lines[i]:  # Export type/variable change
                        data_dict[old_name]['end_line'] = i - 5
                        df_header = data_dict[old_name]['df_header']
                        start = data_dict[old_name]['start_line']
                        nrows = data_dict[old_name]['end_line'] - data_dict[old_name]['start_line']
                        df = make_df(lines, start, nrows, df_header)
                        data_dict[old_name]['Data'] = df
                        varchange = True

                    elif "Analysis begun on" in lines[i]:  # Catch last item to be parsed
                        main_logger.info("EPASWMM Model: " + lines[i].strip())
                        data_dict[old_name]['end_line'] = i - 3
                        df_header = data_dict[old_name]['df_header']
                        start = data_dict[old_name]['start_line']
                        nrows = data_dict[old_name]['end_line'] - data_dict[old_name]['start_line']
                        df = make_df(lines, start, nrows, df_header)
                        data_dict[old_name]['Data'] = df
                    elif "Analysis ended on" in lines[i]:
                        main_logger.info("EPASWMM Model: " + lines[i].strip())
                    elif "Total elapsed time" in lines[i]:
                        main_logger.info("EPASWMM Model: " + lines[i].strip())
                        break
                    else:
                        old_name = new_name
                except Exception:
                    main_logger.error(
                        "While parsing SWMM output RPT file, error encountered on line# {0}: {1}".format(str(i + 1),
                                                                                                         lines[i]))
                    stop_program()
            if len(data_dict) == 0:
                main_logger.error(
                    "Error raised due to detected empty Time Series.  Check result file from EPA SWMM model output: %s" % (
                        rpt_input_file))
                stop_program()
            else:
                main_logger.debug("Done parsing *.rpt file.")
        return data_dict
    except Exception:
        main_logger.error("Error encountered while opening: {0}.".format(rpt_input_file))
        stop_program()


def read_run_info(run_info_file):
    """ 
    Read FEWS run_info.xml file.
    """
    global run_info
    run_info = {}

    if not os.path.exists(run_info_file):
        main_logger.error("Failed to find run_info file: " + str(run_info_file))
        print("Failed to parse run_info file: {0}.\nCheck the adapter log: {1}.".format(str(run_info_file),
                                                                                        logger_filename))  # can't write run_diagnsotics, because if run_info is not found, then we don't know where to write
        sys.exit(1)

    try:
        tree = ET.parse(run_info_file)
        root = tree.getroot()
    except Exception:
        main_logger.error("Failed to parse run_info file.")
        print("Failed to parse run_info file.; check:" + logger_filename)
        sys.exit(1)

    run_info["diagnostic_xml"] = file_element(root.find("pi:outputDiagnosticFile", namespace), exists=False)
    run_info["workDir"] = dir_element(root.find("pi:workDir", namespace).text, exists=True)

    st = time_element(root.find("pi:startDateTime", namespace))
    et = time_element(root.find("pi:endDateTime", namespace))
    t0 = time_element(root.find("pi:time0", namespace))
    lobs = time_element(root.find("pi:lastObservationDateTime", namespace))
    tz = root.find("pi:timeZone", namespace).text
    run_info["start_time"] = pd.Timestamp(st)
    run_info["end_time"] = pd.Timestamp(et)
    run_info["time0"] = pd.Timestamp(t0)
    run_info["last_obs_time"] = pd.Timestamp(lobs)
    run_info["time_zone"] = float(tz)

    # The Rating Curve and the Control Rule files are optional inptus
    if root.find("pi:inputRatingCurveFile", namespace) is not None:
        run_info["dam_rating_curve"] = file_element(root.find("pi:inputRatingCurveFile", namespace).text, exists=True)
    else:
        main_logger.info("No rating curve file provided in the run_info.xml; rating curves will not be updated.")
        print("No rating curve file provided in the run_info.xml; rating curves will not be updated.")


    if root.find("pi:inputTimeSeriesFile", namespace) is not None:
        if os.path.basename(root.find("pi:inputTimeSeriesFile", namespace).text) == "Control_rules.xml":
            run_info["control_rule"] = file_element(root.find("pi:inputTimeSeriesFile", namespace),exists=True)
        else:
            main_logger.info("Time series file was provided, but is not is not considered a Control Rules file. Control_rules.xml is expected.")
            print("Time series file was provided, but is not is not considered a Control Rules file. Control_rules.xml is expected.")
    else:
        main_logger.info("No control rule file (Control_rules.xml) provided in the run_info.xml; control rules will not be updated.")
        print("No control rule file (Control_rules.xml) provided in the run_info.xml; control rules will not be updated.")

    run_info["netcdf"] = file_element(root.find("pi:inputNetcdfFile", namespace))


    # To keep the number of configuration files to a minimum,
    # we put extra properties in the run_info.xml
    properties = root.find("pi:properties", namespace)
    run_info["properties"] = {}
    for e in properties.findall("pi:string", namespace):
        key = e.get("key")
        val = e.get("value")
        path = file_element(val, exists=True)  # currently, the two files are in the properties section are: 1) SWMM exe, 2) SWMM inp file; both should exist
        run_info["properties"][key] = path

    # Hardwired properties
    swmm_input_path = run_info["properties"]["swmm_input_file"]
    swmm_input_fn = os.path.splitext(os.path.basename(swmm_input_path))[0]
    run_info["properties"]["UDUNITS"] = file_element(
        str(Path(run_info_file).parents[0]) + "//model//UDUNITS_lookup.csv", exists=True)
    run_info["properties"]["out_nodes_netcdf"] = file_element(
        str(Path(run_info_file).parents[0]) + "//output//" + swmm_input_fn + "_output_nodes.nc", exists=False)
    run_info["properties"]["out_links_netcdf"] = file_element(
        str(Path(run_info_file).parents[0]) + "//output//" + swmm_input_fn + "_output_links.nc", exists=False)
    run_info["properties"]["swmm_output_file"] = file_element(
        str(Path(run_info_file).parents[0]) + "//model//" + swmm_input_fn + ".rpt", exists=False)
    return run_info


def read_rating_curve(rating_curve_file):
    """
    Reads the dam rating curve XML file, and returns a dictionary with pairs of a) location and b) a string (formatted for use with SWMM)
    """
    try:
        tree = ET.parse(rating_curve_file)
        root = tree.getroot()
        curves = root.findall("pi:ratingCurve", namespace)
    except Exception:
        main_logger.error("Failed to parse rating curve file.")
        stop_program()

    if len(curves) == 0:
        main_logger.error("No rating curves provided in {0}.".format(rating_curve_file))
        stop_program()
        raise ValueError("No rating curves found in the rating curve XML file {0}.".format(rating_curve_file))

    dict_rc = dict()
    loc_list = []
    for curve in curves:
        for item in curve.findall("pi:header", namespace):
            loc = item.find("pi:locationId", namespace).text
            try:
                loc_list = loc_list + [loc]
                unit = item.find("pi:stageUnit", namespace).text
                for table in curve.findall("pi:table", namespace):
                    rows = table.findall("pi:row", namespace)
                    rating_curve_string = ""
                    i = 0
                    for r in rows:
                        if i == 0:
                            rating_curve_string = loc + "     " + "Rating" + "     " + r.get('stage') + "     " + \
                                                  r.get('discharge') + '\n'
                        else:
                            rating_curve_string = rating_curve_string + loc + "     " + "     " + "     " + \
                                                  r.get('stage') + "     " + r.get('discharge') + '\n'
                        i += 1
                dict_rc[loc] = rating_curve_string
            except Exception:
                print("Failed to extract rating curve for: " + loc)
                main_logger.error("Failed to extract rating curve for: " + loc)
                stop_program()
    if len(loc_list) != len(set(loc_list)):
        main_logger.error("Multiple curves with the same name found in {0}".format(rating_curve_file))
        stop_program()
    if len(loc_list) >= 1:
        main_logger.info(
            "{0} rating curves provided in {1}: {2}".format(len(loc_list), str(rating_curve_file), loc_list))
    else:
        main_logger.error("No rating curves provided in {0}.".format(rating_curve_file))
    return dict_rc


def read_control_rules(control_rule_file):
    tree = ET.parse(control_rule_file)
    root = tree.getroot()
    tseries = root.findall("pi:series", namespace)

    dict_rules = dict()
    rule_list = []
    j = 0

    for s in tseries:
        rating_curve_string = ''
        for item in s.findall("pi:header", namespace):
            param = item.find("pi:parameterId", namespace).text
            loc = item.find("pi:locationId", namespace).text
            missing_value = item.find("pi:missVal", namespace).text

            rule_id = loc + '-' + param  # unique identifier of these time series rules
            rule_list = rule_list + [rule_id]

        events = s.findall("pi:event", namespace)
        i = 0
        for e in events:
            # convert date format for epaswmm
            if e.get('value') != missing_value:
                d = time_element(e)
                rating_curve_string = rating_curve_string + 'Rule ' + 'AdapterRule' + str(j + 1) + '.' + str(
                    i + 1) + '\n' + \
                                      'IF SIMULATION DATE = ' + d.strftime('%m/%d/%Y') + '\n' \
                                      'AND SIMULATION CLOCKTIME = ' + d.strftime("%H:%M:%S") + '\n' \
                                      'THEN' + ' ' + param + ' ' + loc + ' ' + 'SETTING = ' + e.get('value') + '\n\n'
                i += 1
        dict_rules[rule_id] = rating_curve_string
        j += 1

    if len(rule_list) != len(set(rule_list)):
        main_logger.error("Multiple rule time series for the same location-type pair (e.g. OL341-OUTLET) found in {0}".format(
            control_rule_file))
        stop_program()

    return dict_rules

def read_units(units_input_file):
    """
    Read the relate table between EPA-SWMM and UDUNITS + attributes information
    """
    swmm_unit_dict = {}
    try:
        with open(units_input_file) as f:
            lines = f.readlines()
            header = lines[0].strip().split(',')
            for i in range(1, len(lines)):
                aline = lines[i].strip().split(',')
                temp = {}
                temp = {header[1]: aline[1], header[2]: aline[2], header[3]: aline[3]}
                swmm_unit_dict[aline[0]] = temp
    except Exception:
        main_logger.error("Error parsing UDUNITS input file: %s" % units_input_file)
        stop_program()
    return swmm_unit_dict

def stop_program():
    """
    Used when an error is encountered:
    - Read the adapter log
    - Write errors to run_diagnostics.xml
    - Exit program execution.
    """
    if "pytest" in sys.modules:
        xml = r"log/run_diagnostic_test_cases.xml"
    else:
        xml = run_info["diagnostic_xml"]
    main_logger.error(
        "STOPPING ADAPTER : Error encountered while running the adapter. Reading Adapter Log, and writing the Diagnostics File and exiting.")
    df = read_errors_warnings([logger_filename])
    write_run_diagnostics(df, xml)
    sys.exit(1)

def time_element(elem):
    """
    Get datetime from XML element with date and time attributes
    """
    start_str = elem.get("date") + " " + elem.get("time")
    try:
        dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        main_logger.error("Failed to parse date/time:" + str(start_str))
        stop_program()
    return dt

def write_netcdf(ds, ds_fn):
    """
    Write a DataSet to NetCDF format.
    """
    try:
        ds.to_netcdf(ds_fn, mode='w')
    except Exception:
        main_logger.error("Failed to write dataset to:" + str(ds_fn))
        stop_program()


def write_rainfall(rainfall_net_cdf, rainfall_dat, col_to_convert=['station_id', 'station_names']):
    """
    Reads the rainfall NetCDF file, converts column type (unicode).
    Write the rainfall in SWMM .DAT format.
    """
    df_rain = read_netcdf(rainfall_net_cdf, col_to_convert)
    df_rain = df_rain.reset_index()[["station_id", "time", "P"]]
    df_rain['year'] = df_rain['time'].dt.year
    df_rain['month'] = df_rain['time'].dt.month
    df_rain['day'] = df_rain['time'].dt.day
    df_rain['hour'] = df_rain['time'].dt.hour
    df_rain['minute'] = df_rain['time'].dt.minute
    df_rain = df_rain[["station_id", "year", "month", "day", "hour", "minute", "P"]]
    df_rain.to_csv(rainfall_dat, sep=" ", header=[";Rainfall"] + (len(df_rain.columns) - 1) * [""],
                   escapechar="\\", quoting=csv.QUOTE_NONE, index=False)
    main_logger.info(
        "Converted the NetCDF rainfall file ({0}) to EPASWMM .DAT format ({1}).".format(rainfall_net_cdf, rainfall_dat))


def write_run_diagnostics(df_err_warn, run_diagnostics):
    """
    Write the dataframe that contains both Python and EPASWMM errors to the run diagnostics file, in FEWS PI XML format.
    """
    try:
        with open(run_diagnostics, 'w') as xf:
            # Write Header
            xf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            xf.write('<Diag xmlns="http://www.wldelft.nl/fews/PI"\n')
            xf.write('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
            xf.write(
                'xsi:schemaLocation="http://www.wldelft.nl/fews/PI http://fews.wldelft.nl/schemas/version1.0/pi-schemas/pi_diag.xsd" version="1.2">\n')

            # Write Warnings Errors
            if len(df_err_warn) > 0:
                for index, row in df_err_warn.iterrows():
                    loc_text = str('            <line level="%s" description="%s"/>\n') % (
                        row["level"], row["description"])
                    xf.write(loc_text)
            else:
                xf.write(
                    '            <line level="2" description="No errors, warnings or info messages were detected in the EPASWMM output or adapter log."/>\n')
            xf.write('</Diag>')

    except IOError:
        print("Error writing the run diagnostics file: {0}".format(run_diagnostics))
        main_logger.error("Error writing the run diagnostics file.".format(run_diagnostics))
        sys.exit(1)
        # not using stop_program(), since stop_program() uses write_run_diagnostics()


def write_runfile(run_info, rating_curve, control_rule):
    """ 
    Use template file to create the input file required by EPA SWMM.
    """
    filein = run_info["properties"]["swmm_input_file"]
    filetmp = os.getcwd() + "//model//temp.inp"

    dict_options = {
        "START_DATE": "START_DATE".ljust(21, " ") + run_info["start_time"].strftime("%m/%d/%Y"),
        "START_TIME": "START_TIME".ljust(21, " ") + run_info["start_time"].strftime("%H:%M:%S"),
        "END_DATE": "END_DATE".ljust(21, " ") + run_info["end_time"].strftime("%m/%d/%Y"),
        "END_TIME": "END_TIME".ljust(21, " ") + run_info["end_time"].strftime("%H:%M:%S"),
        "REPORT_START_DATE": "REPORT_START_DATE".ljust(21, " ") + run_info["start_time"].strftime("%m/%d/%Y"),
        'REPORT_START_TIME': "REPORT_START_TIME".ljust(21, " ") + run_info["start_time"].strftime("%H:%M:%S")
    }

    replace_key = None
    write_original = True
    set_curves = set()
    previous_section = None
    current_section = None
    control_rules_exist = False
    section_switch = False
    main_logger.debug(rating_curve)

    if not os.path.exists(filein):
        main_logger.error("Expected file was not found: " + str(filein))
        stop_program()
        raise IOError("Expected file was not found: " + str(filein))

    try:
        with open(filein) as f_in:
            with open(filetmp, "w") as f_out:
                for num, line in enumerate(f_in, 1):
                    # Checking which section we are in:
                    if re.match(r'\[', line) is not None:  # CHECK which section we are in
                        previous_section = current_section
                        current_section = line.strip()
                        section_switch = True

                        if line.strip() == "[CONTROLS]":
                            control_rules_exist = True
                    else:
                        section_switch = False


                    # Updating the "CONTROLS" section ***************************
                    # Appending to the end of the section for clarity in the INP File
                    if section_switch == True and previous_section == "[CONTROLS]":
                        for key, value in control_rule.items():
                            f_out.write(value)
                        f_out.write(line)


                    # Updating the "OPTIONS" section ***************************
                    elif current_section == "[OPTIONS]":
                        # Checking if one of the keys to replace is in the line
                        for key in dict_options:
                            if re.match(key + '\\b', line) is not None:
                                replace_key = key
                        # Replacing the line with the desired text
                        if replace_key is not None:
                            f_out.write(dict_options[replace_key] + "\n")
                        else:
                            f_out.write(line)
                        replace_key = None

                    # Updating the "RATING CURVE" section ***************************
                    elif current_section == "[CURVES]":
                        main_logger.debug(" --> " + str(num) + line)
                        if not bool(rating_curve):
                            main_logger.debug(rating_curve)
                            main_logger.debug(
                                "No rating curves found when updating the [CURVES] section. No updates will be made to this section.")
                        elif bool(rating_curve):
                            if len(line.split()) == 4 and line.split()[1] == 'Rating':
                                curve_id = line.split()[0]
                                set_curves.add(curve_id)
                                # Check if a match exists in the XML file
                                write_original = False  # first, assume the curve doesn't need to be replaced
                                for key, value in rating_curve.items():
                                    if curve_id != key:
                                        main_logger.debug(
                                            "The XML curve {0} does not match the current INP storage curve. Will continue checking other curves in the XML".format(
                                                key, curve_id))
                                        write_original = True
                                    elif curve_id == key:
                                        write_original = False
                                        main_logger.info("Using the curve from the XML file for: " + key)
                                        f_out.write(value)
                                        break  # stop checking the XML
                            elif line == '\n' or line.startswith(";"):
                                write_original = True
                        if write_original:
                            main_logger.debug("Writing: " + line.strip())
                            f_out.write(line)

                    else:
                        f_out.write(line)

            if control_rules_exist is False and len(control_rule) > 0:
                main_logger.error("No control rules in INP file, control rules were provided by FEWS. If control" \
                                  "rules are required, add a default control rule to the INP file.")
                stop_program()

    except IOError:
        print("Error writing the model run file: {0}".format(filetmp))
        main_logger.error("Error writing the model run file: {0}".format(filetmp))

    try:
        move(filetmp, filein)
    except OSError:
        main_logger.error("Error when updating the INP file; trying to overwrite {0} with {1}.".format(filein, filetmp))

    if len(set(rating_curve.keys())) > 0 and len(set(rating_curve.keys()) - set_curves) > 0:
        main_logger.warning(
            "Curve(s) exported from FEWS, but does not have a match in the INP file. It is being ignored." + str(
                set(rating_curve.keys()) - set_curves))


#####################################################
# MAIN METHODS
#####################################################

def pre_adapter():
    """
    Pre-Adapter method.
    """
    print("\n\n\n##### Running Pre-Adapter EPA-SWMM Delft-FEWS for {0} ...\n".format(args.run_info))
    main_logger.info("##### Running Pre-Adapter EPA-SWMM Delft-FEWS for {0} ...".format(args.run_info))


    if run_info_file is None or not run_info_file.exists():
        main_logger.error(f"'run_info.xml' not found in {os.getcwd()}")
        raise AssertionError(f"'run_info.xml' not found in {os.getcwd()}")
    else:
        run_info = read_run_info(run_info_file)
        properties = run_info["properties"]

    # Read Rating Curve
    if "dam_rating_curve" in run_info.keys():
        rc_dict = read_rating_curve(run_info["dam_rating_curve"])
    else:
        rc_dict = dict()

    # Read Control Rules
    if "control_rule" in run_info.keys():
        rule_dict = read_control_rules(run_info["control_rule"])
    else:
        rule_dict = dict()

    # Writing EPA SWMM input file
    write_runfile(run_info, rc_dict, rule_dict)
    print("\nRun Info content: \n", run_info)

    # Writing rainfall file from netCDF format received from FEWS.
    rainfall_dat = os.getcwd() + "//model//rain.dat"
    write_rainfall(run_info["netcdf"], rainfall_dat)
    print("\nDone writing {0} file.\n".format(rainfall_dat))

    try:
        print("\n   -->     Reading warnings and errors...")
        main_logger.info("Reading warnings and errors from: {0}".format(logger_filename))
        main_logger.info("##### Completed Pre-Adapter EPA-SWMM Delft-FEWS".format(logger_filename))
        print("\n   -->     Writing Diagnostic file...\n")
        df_err_warn = read_errors_warnings([logger_filename])
        write_run_diagnostics(df_err_warn, run_info["diagnostic_xml"])

    except Exception:
        main_logger.error(
            "Errors occurred while checking the log file for warnings and errors. Check {0}.".format(logger_filename))
        raise ValueError(
            "Errors occurred while checking the log file for warnings and errors. Check {0}.".format(logger_filename))


def run_model():
    """
    Running model...
    This method is intended for testing the adapter.
    The normal workflow will be that FEWS initiates the model adapter.
    """
    print("\n\n\n##### Running EPA-SWMM model for {0} ...\n".format(args.run_info))
    main_logger.info("##### Running EPA-SWMM model for {0} ...".format(args.run_info))

    if run_info_file is None or not run_info_file.exists():
        main_logger.error(f"'run_info.xml' not found in {os.getcwd()}")
        raise AssertionError(f"'run_info.xml' not found in {os.getcwd()}")
    else:
        run_info = read_run_info(run_info_file)
        properties = run_info["properties"]

    model_bin = run_info["properties"]["model-executable"]
    main_logger.info("Model executable being used to run SWMM model: {0}".format(str(model_bin)))
    os.chdir(str(run_info["workDir"]))  # current directory must be the model folder in order for the SWM .inp's reference to the rain.dat to work. WorkDir in Run Info refers to the "model" folder
    with open('Run_model.bat', "w") as bf:
        bf.write(str(model_bin) + " " + str(run_info["properties"]["swmm_input_file"]) + " " + str(
            run_info["properties"]["swmm_output_file"]))
    output = subprocess.run([str(model_bin), str(run_info["properties"]["swmm_input_file"]),
                             str(run_info["properties"]["swmm_output_file"])], check=True)
    os.chdir(run_info["workDir"]) # change back to working directory


    try:
        print("\n   -->     Reading warnings and errors...")
        main_logger.info("Reading warnings and errors from: {0}".format(properties["swmm_output_file"]))

        print("\n   -->     Writing Diagnostic file...\n")
        df_err_warn = read_errors_warnings([logger_filename])
        write_run_diagnostics(df_err_warn, run_info["diagnostic_xml"])
    except Exception:
        main_logger.error(
            "Errors occurred while checking the SWMM model output for warnings and errors. Check {0}.".format(
                logger_filename))
        raise ValueError(
            "Errors occurred while checking the SWMM model output for warnings and errors. Check {0}.".format(
                logger_filename))
    return output


def post_adapter():
    """
    Post-Adapter Method.
    """
    if __name__ == "__main__":
        print("\n\n\n##### Running Post-Adapter EPA-SWMM Delft-FEWS for {0} ...\n".format(args.run_info))
        main_logger.info("##### Running Post-Adapter EPA-SWMM Delft-FEWS for {0}".format(args.run_info))

        if run_info_file is None or not run_info_file.exists():
            main_logger.error(f"'run_info.xml' not found in {os.getcwd()}")
            raise AssertionError(f"'run_info.xml' not found in {os.getcwd()}")
        else:
            run_info = read_run_info(run_info_file)
            properties = run_info["properties"]

            print("\n   -->     Checking SWMM for warnings and errors...")
            main_logger.info("Checking SWMM for warnings and errors: {0}".format(properties["swmm_output_file"]))

        # If the output file doesn't exist, read the adapter log and make run_diagnostics
        if not os.path.exists(properties["swmm_output_file"]):
            main_logger.error("Was not able to find {0}".format(properties["swmm_output_file"]))
            stop_program()
        else:  # if output file exists, try reading errors and warning
            try:
                df_swmm_err = read_errors_warnings([properties["swmm_output_file"]])
            except Exception:
                main_logger.error(
                    "Errors occurred while checking the SWMM model output for warnings and errors. Check {0}.".format(
                        properties["swmm_output_file"]))
                raise IOError(
                    "Errors occurred while checking the SWMM model output for warnings and errors. Check {0}.".format(
                        properties["swmm_output_file"]))

            # IF NO ERRORS:

        if len(df_swmm_err[df_swmm_err['level'] == 1]) == 0:  # level 1 corresponds to error
            # Read EPA SWMM Units and attributes
            print("\n   -->     No SWMM Errors Found, proceeding...\n")
            main_logger.info("No SWMM errors found, proceeding with parsing the RPT file: {0}".format(
                properties["swmm_output_file"]))

            print("   -->     Reading units...\n")
            swmm_unit_dict = read_units(properties["UDUNITS"])
            main_logger.info("Reading units lookup table: {0}".format(properties["UDUNITS"]))

            # Read EPA SWMM results from *.rpt output file.
            print("   -->     Reading results into a DataFrame...\n")
            data_dict = read_rpt_file(properties["swmm_output_file"])
            main_logger.info("Reading results into a DataFrame: {0}".format(properties["swmm_output_file"]))

            print("\n   -->     Creating DataSet from the results DataFrame...\n")
            main_logger.info("Creating DataSet from the results DataFrame.".format(properties["UDUNITS"]))
            combined_ds_nodes, combined_ds_links = create_xarray_dataset(data_dict, swmm_unit_dict)

            print("\n   -->     Writing nodes netCDF output file...\n")
            main_logger.info("Writing nodes netCDF output file: {0}".format(properties["out_nodes_netcdf"]))
            write_netcdf(combined_ds_nodes, properties["out_nodes_netcdf"])

            print("\n   -->     Writing links netCDF output file...\n")
            main_logger.info("Writing links netCDF output file: {0}".format(properties["out_links_netcdf"]))
            write_netcdf(combined_ds_links, properties["out_links_netcdf"])

            print("\n####### Post-Adapter process completed successfully!")
            main_logger.info("###### Post-Adapter process completed successfully!")

        else:
            main_logger.error(
                "Errors were detected in the model simulation.  See run_diagnostic.xml file for more details.")
            raise Warning(
                "Errors were detected in the model simulation.  See run_diagnostic.xml file for more details.")

        try:
            print("\n   -->     Reading Python Log...")
            main_logger.info("Reading adapter log, writing adapter log and SWMM errors/warnings in FEWS format.")
            df_python_err_warn = read_errors_warnings(
                [logger_filename])  # even though SWMM log was read earlier, easier to just re-read it here.
            print("\n   -->     Writing Diagnostic file...\n")
            write_run_diagnostics(pd.concat([df_python_err_warn, df_swmm_err]), run_info["diagnostic_xml"])

        except Exception:
            main_logger.error(
                "Errors occurred while checking the SWMM model output for warnings and errors. Check {0} and {1}.".format(
                    properties["swmm_output_file"],
                    logger_filename))
            raise ValueError(
                "Errors occurred while checking the SWMM model output for warnings and errors. Check {0} and {1}.".format(
                    properties["swmm_output_file"],
                    logger_filename))



###############################################################
# Execute only if run as a script
#
# MAIN CODE
#
###############################################################
def setup_logger(name, log_file, logging_level=logging.INFO):
    """Sets up a logger handler.
     A separate logger will be initiated for each of the commands (pre/run/post)."""
    try:
        os.remove(log_file)
    except Exception:
        pass
    formatter = logging.Formatter('%(levelname)s: External Adapter - %(message)s (%(asctime)s)')
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    return logger

if __name__ == "__main__":
    parser = ap.ArgumentParser(description="TRCA-FEWS adapter for EPASWMM models")
    parser.set_defaults(func=parser.print_usage)

    parser.add_argument('--run_info', dest='run_info', required=True,
                        help='Full path to the run_info.xml file.')

    subparsers = parser.add_subparsers(
        title="subcommands", description="valid subcommands", help="additional help"
    )

    # create the parser for the "pre" command
    help_pre = "Prepare the EPASWMM model"
    parser_pre = subparsers.add_parser("pre", help=help_pre)
    parser_pre.set_defaults(func=pre_adapter)

    # create the parser for the "run" command
    help_run = "Run the EPASWMM model"
    parser_run = subparsers.add_parser("run", help=help_run)
    parser_run.set_defaults(func=run_model)

    # create the parser for the "post" command
    help_pos = "Set the EPASWMM output files for Delft-FEWS"
    parser_post = subparsers.add_parser("post", help=help_pos)
    parser_post.set_defaults(func=post_adapter)

    args = parser.parse_args()
    run_info_file = Path(args.run_info)
    os.chdir(Path(run_info_file).parents[0])  # os.getcwd()+"//"+args.model)

    # DEFINE the logger file name; different logger for each adapter.
    logger_filename = os.getcwd() + "//model_adapter.log"
    if args.func.__name__ == "pre_adapter":
        logger_filename = str(Path(run_info_file).parents[0]) + "//log//pre_adapter.log"

    elif args.func.__name__ == "run_model":
        logger_filename = str(Path(run_info_file).parents[0]) + "//log//run_adapter.log"

    elif args.func.__name__ == "post_adapter":
        logger_filename = str(Path(run_info_file).parents[0]) + "//log//post_adapter.log"

    main_logger = setup_logger('EPASWMM FEWS Python Logger', logger_filename, logging.INFO)
    args.func()

else:
    logger_filename = os.getcwd() + "//model_adapter.log"  # when running from Python, do not save to Log folder
    print(logger_filename)
    main_logger = setup_logger('EPASWMM FEWS Python Logger', logger_filename, logging.DEBUG)
    main_logger.info(
        "Log written to root directory. When run from the command line, log will be written to the 'log' folder.")