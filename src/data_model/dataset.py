from copy import deepcopy
from datetime import datetime
import io
import json
from typing import Any, Dict, List, Optional

import pandas as pd
from pandasql import sqldf

from datalake_driver.i_driver import IDriver


class Dataset:
    """
    'Dataset' class - implements only inner logic of dataset (reading, writing, etc).
    All other operations are implementing by datalake.

    Main atributes:
    - name: dataset name
    - descr: dataset text descriptions
    - metadata_schema_descr: description of metadata fields
    - metadata_table: table of files and its metadata
    - driver: storaging driver

    TODO section:
    - Make optimization by splitting 'metadata_schema' on 'common_fields'
        (where values of md are common for each data), and 'specific_fields' (where values are different)
    - Maybe it is important to switch from pandas table storaging for some specific class/different framework for tabular data
    """

    ### variables of dataset
    __name: str = None
    __descr: str = None
    __metadata_schema_descr: Dict[str, str] = None
    __metadata_table: pd.DataFrame = None
    __driver: IDriver = None
    __datasets_cataloque: str = None

    ### common constants
    # file operating consts
    __DESCR_FILE = "description.json"
    __MD_FILE = "metadata.csv"

    # dict description consts
    __NAME_FIELD = "name"
    __DESCR_FIELD = "descr"
    __MD_SCHEMA_DESCR_FIELD = "md_schema_descr"

    # additional metadata fields consts
    __ID_MD_FIELD = "id"
    __FILENAME_MD_FIELD = "file"
    __TIME_MD_FIELD = "time"

    def __init__(self):
        return

    def create_dataset(
        self,
        dataset_name: str,
        driver_instance: IDriver,
        datasets_cataloque: str,
        description: str,
        metadata_schema_descr: Dict[str, str],
    ):
        self.__name = dataset_name
        self.__driver = driver_instance
        self.__datasets_cataloque = datasets_cataloque

        self.__descr = description
        self.__metadata_schema_descr = metadata_schema_descr

        
        cols = [self.__ID_MD_FIELD, self.__FILENAME_MD_FIELD, self.__TIME_MD_FIELD] + list(
            self.__metadata_schema_descr.keys()
        )
        dtype_map: Dict[str, str] = {
            self.__ID_MD_FIELD: "int64",
            self.__FILENAME_MD_FIELD: "object",
            self.__TIME_MD_FIELD: "datetime64[ns]",
        }
        for k, meta in (self.__metadata_schema_descr or {}).items():
            t = meta.get("type") if isinstance(meta, dict) else None
            if t == "int":
                dtype_map[k] = "int64"
            elif t == "float":
                dtype_map[k] = "float64"
            elif t == "bool":
                dtype_map[k] = "bool"
            else:
                dtype_map[k] = "object"

        self.__metadata_table = pd.DataFrame({c: pd.Series(dtype=dtype_map.get(c, "object")) for c in cols})

        self.save_state()
        return

    def read_dataset(
        self, dataset_name: str, driver_instance: IDriver, datasets_cataloque: str
    ):
        self.__name = dataset_name
        self.__driver = driver_instance
        self.__datasets_cataloque = datasets_cataloque

        dict_bytes = self.__driver.get(self.__DESCR_FILE, self.__datasets_cataloque)
        byte_stream = io.BytesIO(dict_bytes)
        data = json.load(byte_stream)

        self.__descr = data[self.__DESCR_FIELD]
        self.__metadata_schema_descr = data[self.__MD_SCHEMA_DESCR_FIELD]

        csv_bytes = self.__driver.get(self.__MD_FILE, self.__datasets_cataloque)
        byte_stream = io.BytesIO(csv_bytes)
        self.__metadata_table = pd.read_csv(byte_stream)
        return

    def add_file_obj(
        self,
        file: bytearray,
        filename: str,
        files_metadata: Dict[str, Any],
        skip_values: bool = False,
    ):
        """
        Ading data to dataset

        :param file: file in bytearray type
        :type file: bytearray
        :param filename: Description
        :type filename: str
        :param files_metadata: Description
        :type files_metadata: Dict[str, Any]
        """

        # 0 - check fields
        new_file_md_keys = set(files_metadata.keys())
        required_md_keys = set(self.__metadata_schema_descr.keys())
        if new_file_md_keys != required_md_keys and skip_values == False:
            missed = required_md_keys - new_file_md_keys
            unexpected = new_file_md_keys - required_md_keys
            raise ValueError(
                f"There are some misulighment with expected metadata. There are missed in original schema fields ({missed}), and there are unexpected values ({unexpected})"
            )

        files_metadata_tmp = deepcopy(files_metadata)
        missed = list(required_md_keys - new_file_md_keys)
        if skip_values == True and len(missed) != 0:
            files_metadata_tmp.update({skipped_k: None for skipped_k in missed})

        # 1 - add 'working' fields - path id time etc
        adding_date = datetime.now()
        files_metadata_tmp.update(
            {
                self.__ID_MD_FIELD: len(self.__metadata_table.index),
                self.__FILENAME_MD_FIELD: filename,
                self.__TIME_MD_FIELD: adding_date,
            }
        )

        # IMPORTANT: keep `id` as a regular column (not as DataFrame index).
        # Otherwise it gets lost when saving with index=False and becomes NaN on reload.
        #
        # Also: preserve column dtypes. A plain `.loc[...] = Series(dtype=object)` will upcast
        # the whole table to object dtype, and then pandasql/sqlite may serialize numeric values
        # as BLOB, breaking numeric comparisons in retrieval benchmarks.
        new_row_df = pd.DataFrame([files_metadata_tmp]).reindex(columns=self.__metadata_table.columns)
        for c in new_row_df.columns:
            try:
                target = self.__metadata_table[c].dtype
                if str(target).startswith("datetime64"):
                    new_row_df[c] = pd.to_datetime(new_row_df[c])
                else:
                    new_row_df[c] = new_row_df[c].astype(target)
            except Exception:
                # best-effort casting; keep original if conversion fails
                pass

        if self.__metadata_table is None or len(self.__metadata_table.index) == 0:
            self.__metadata_table = new_row_df
        else:
            self.__metadata_table = pd.concat([self.__metadata_table, new_row_df], ignore_index=True)
        # TODO: make storaging in new catalogue, which will storage the file and all his additional material from computing
        self.__driver.write(file, filename, self.__datasets_cataloque)

        # 3 - save state
        self.save_state()
        return

    def get_base_info_str(self) -> str:
        info_str = f"Name: '{self.__name}'\n" + f"Descr: '{self.__descr}'\n"

        return info_str

    def get_info_str(self) -> str:
        info_str = (
            f"Name: '{self.__name}'\n"
            + f"Descr: '{self.__descr}'\n"
            + f"Metadata schema:\n"
        )

        md_schema_str = "\n".join(
            f" - '{fn}' field: {fd};" for fn, fd in self.__metadata_schema_descr.items()
        )
        return info_str + md_schema_str

    def get_md_schema_descr(self) -> Dict[str, str]:
        return self.__metadata_schema_descr

    def get_data_table(self, sql_request: str) -> pd.DataFrame:
        df = self.__metadata_table
        result_df = sqldf(sql_request, locals())
        return result_df

    def get_data_full(self, sql_request: str) -> pd.DataFrame:
        # TODO
        pass

    def save_state(self):
        dict_info = {
            self.__NAME_FIELD: self.__name,
            self.__DESCR_FIELD: self.__descr,
            self.__MD_SCHEMA_DESCR_FIELD: self.__metadata_schema_descr,
        }

        self.__driver.write(
            bytearray(json.dumps(dict_info), "utf-8"),
            self.__DESCR_FILE,
            self.__datasets_cataloque,
        )

        buffer = io.BytesIO()
        self.__metadata_table.to_csv(buffer, index=False, encoding="utf-8")
        buffer.seek(0)
        ba = bytearray(buffer.read())

        self.__driver.write(ba, self.__MD_FILE, self.__datasets_cataloque)
        return
