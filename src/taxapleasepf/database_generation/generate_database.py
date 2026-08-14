#!/usr/bin/env python3
import os
import csv
import datetime
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd  # type: ignore
import requests  # type: ignore

#####################
# Utility functions #
#####################


def download_file(url, *, destinationDir=None):
    """
    Nicked from https://stackoverflow.com/a/16696317
    It's a large file so we don't just load it all into memory

    A destination directory can optionally be specified
    If not specified, we use the current working directory
    """
    if not destinationDir:
        destinationDir = Path.cwd()

    local_filename = Path(destinationDir, url.split("/")[-1])

    ## NOTE the stream=True parameter below
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with Path.open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                # if chunk:
                f.write(chunk)

    return local_filename


def main(tempdir, *, ncbi_taxonomy_data_url=None, db_path=None):
    start_time = datetime.datetime.now()

    ## default URL if not specified
    if not ncbi_taxonomy_data_url:
        ncbi_taxonomy_data_url = (
            "https://genome-idx.s3.amazonaws.com/kraken/pluspf_20260626/inspect.txt"
        )

    #######################################
    # Downloading and extracting the data #
    #######################################

    ## download the data
    print(f"{datetime.datetime.now()} Downloading {ncbi_taxonomy_data_url}")
    ncbi_taxonomy_data_compressed = download_file(
        ncbi_taxonomy_data_url, destinationDir=tempdir
    )

    ##################################
    # Processing the downloaded data #
    ##################################

    parent_lookup_dict = {}

    tempoutfilepath = os.path.join(tempdir, "parsed_inspect.csv")

    with open(tempoutfilepath, "w") as outfile:
        csvwriter = csv.writer(outfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        csvwriter.writerow(["taxid", "name", "rank", "parent_taxid"])
        with Path("inspect.txt").open() as infile:
            for idx, line in enumerate(infile):
                if line.startswith("#"):
                    continue
                if not len(line):
                    continue
                splitline = line.split("\t")
                rank = splitline[3]
                taxid = int(splitline[4])
                taxon = splitline[-1].strip()
                indent_count = int(((len(splitline[-1]) - len(taxon)) - 1) / 2)

                parent_lookup_dict[indent_count] = taxid
                if taxid != 1:
                    parent_taxid = parent_lookup_dict[indent_count - 1]
                else:
                    parent_taxid = None

                csvwriter.writerow([str(taxid), taxon, rank, str(parent_taxid)])

    concat_df = pd.read_csv(tempoutfilepath)

    ###################
    # Database ingest #
    ###################

    ## create an sqlite database
    print(f"{datetime.datetime.now()} Staging taxapf.db")
    if not db_path:
        db_dir = Path(Path.home(), ".taxapleasepf")
        db_path = Path(db_dir, "taxapf.db")
    else:
        db_dir = Path(db_path).parent

    conn = sqlite3.connect(db_path)

    ## push the result to the database
    ## should overwrite the table if exists
    print(f"{datetime.datetime.now()} Writing taxa table to {db_path.name}")
    concat_df.to_sql("taxa", con=conn, index_label="taxid", if_exists="replace")

    ## create a metadata table that contains
    ## the current taxdatabase URL
    metadata_table_df = (
        pd.DataFrame([("ncbi_taxonomy_data_url", ncbi_taxonomy_data_url)])
        .rename({0: "key", 1: "value"}, axis=1)
        .set_index("key")
    )

    metadata_table_df.to_sql(
        "metadata", con=conn, index_label="key", if_exists="replace"
    )

    print(f"{datetime.datetime.now()} Done in {datetime.datetime.now() - start_time}")


#################
# Actual script #
#################

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tempdir:
        main(tempdir)
