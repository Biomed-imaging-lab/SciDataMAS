import json
import io
import os
from typing import Any, Dict, List, Callable

import pandas as pd

from data_model.dataset import Dataset
from datalake_driver.i_driver import IDriver


class DatasetInfo:
    name: str = ""
    full_description: str = ""


class Datalake:
    """
    Datalake logic class. Provides logic of storaging (reading/writing) with some catalogization, operating and automatic computation.

    The main idea of catalogisation (on path-placeholder '*f1*/*f2*/*f3*/*data.ext*'):
    - 'f1' - should be the name of organization's datalake
    - 'f2' - should be the name of dataset
    - 'f3' - should be the name of file: it is the private folder for dataset's elements.
        It can contains some additional files - like masks of images, original meta, etc.
    - 'data.ext' - should be the name of data in dataset

    So the example of passed keys/filenames should be 'Main_datalake/imgs_dataset/img1/img1.tiff'

    The info about datalakes storages into specialied file '*f1*/DATALAKE_INFO.json'

    The info about datasets storages into specialied file '*f1*/*f2*/DATASET_INFO.json   '
    """

    # fields for description
    __name: str = None
    __descr: str = None
    __datasets: Dict[str, Dataset] = None

    # fields for operating computes/merge logics
    # datasets_linkage: Dict[
    #     str, List[str]
    # ]  # mapping dataset name to his children's names
    # merge_chains: List[MergingStructure]  # just a list of merging structures

    # fields for operating IO
    __driver: IDriver = None
    __cataloque: str = None

    # consts
    __DATALAKE_INFO_FN: str = "DATALAKE_INFO.json"

    __DATALAKE_NAME_FIELD: str = "name"
    __DATALAKE_DESCR_FIELD: str = "descr"
    __DATALAKE_DATASETS_LIST_FIELD: str = "datasets"
    __DATALAKE_DATASET_NAME_FIELD: str = "name"
    __DATALAKE_DATASET_CATALOQUE_FIELD: str = "cataloque"

    def __dataset_cataloque_naming(self, new_dataset_name: str) -> str:
        return self.__cataloque + f"{new_dataset_name}/"

    # basic init methods
    def __read_datalake(self):
        read_dict_bytes = self.__driver.get(self.__DATALAKE_INFO_FN, self.__cataloque)
        stream = io.BytesIO(read_dict_bytes)
        datalake_dict = json.load(stream)

        self.__name = datalake_dict[self.__DATALAKE_NAME_FIELD]
        self.__descr = datalake_dict[self.__DATALAKE_DESCR_FIELD]

        self.__datasets = {}
        datasets_info = datalake_dict[self.__DATALAKE_DATASETS_LIST_FIELD]
        for ds_info in datasets_info:
            new_dataset = Dataset()
            new_dataset.read_dataset(
                ds_info[self.__DATALAKE_DATASET_NAME_FIELD],
                self.__driver,
                ds_info[self.__DATALAKE_DATASET_CATALOQUE_FIELD],
            )

            self.__datasets[ds_info[self.__DATALAKE_DATASET_NAME_FIELD]] = new_dataset
        return

    def __create_datalake(self):
        self.__datasets = {}
        self.__driver.create_cataloque(self.__cataloque)
        self.save_state()
        return

    def __init__(self, name: str, cataloque: str, driver: IDriver):
        # TODO: split on two different procedures
        self.__name = name
        self.__descr = ""  # description
        self.__cataloque = cataloque
        self.__driver = driver

        cat_exists = self.__driver.is_cataloque_exists(self.__cataloque)
        info_exists = False
        try:
            info_exists = self.__driver.is_exist(self.__DATALAKE_INFO_FN, self.__cataloque)
        except Exception:
            info_exists = False

        if cat_exists and info_exists:
            self.__read_datalake()
        else:
            self.__create_datalake()
        return

    # info retrieving methods
    def get_datalake_info(self) -> List[DatasetInfo]:
        result_list = []
        for name, dataset in self.__datasets.items():
            new_info = DatasetInfo()
            new_info.name = name
            new_info.full_description = dataset.get_base_info_str()
            result_list.append(new_info)
        return result_list

    def get_datalake_info_str(self) -> str:
        info_str = f"Name: '{self.__name}'\n" + f"Description: '{self.__descr}'\n"

        if len(self.__datasets.keys()) == 0:
            info_str += "There is no actual datasets in datalake."
            return info_str

        dataset_list_info = "\n".join(
            [
                f"- '{k}' dataset:\n" + d.get_info_str()
                for k, d in self.__datasets.items()
            ]
        )
        info_str += "Datasets:\n" + dataset_list_info
        return info_str

    def list_datasets(self) -> List[str]:
        return list(self.__datasets.keys())

    def get_datalake_info(self) -> List[str]:
        return [d.get_info_str() for _, d in self.__datasets.items()]

    def get_dataset_md(self, dataset_name: str) -> Dict[str, str]:
        if dataset_name not in self.__datasets.keys():
            raise AttributeError(
                f"There is no such dataset with name '{dataset_name}' in '{self.__name}' datalake!"
            )

        dataset = self.__datasets[dataset_name]
        return dataset.get_md_schema_descr()

    def get_dataset_info_str(self, dataset_name: str) -> str:
        if dataset_name not in self.__datasets.keys():
            raise AttributeError(
                f"There is no such dataset with name '{dataset_name}' in '{self.__name}' datalake!"
            )

        dataset = self.__datasets[dataset_name]
        return dataset.get_info_str()

    # working with files methods
    def get_data_table_sql(self, dataset_name: str, sql_request: str) -> pd.DataFrame:
        if dataset_name not in self.__datasets.keys():
            raise AttributeError(
                f"There is no such dataset with name '{dataset_name}' in '{self.__name}' datalake!"
            )

        result = self.__datasets[dataset_name].get_data_table(sql_request)
        return result

    # TODO
    def get_full_data_sql(self, dataset_name: str, sql_request: str):
        pass

    def add_local_file(
        self,
        dataset_name: str,
        filled_md: Dict[str, Any],
        local_filename: str,
        local_filepath: str,
        skip_values: bool = False,
    ):
        if dataset_name not in self.__datasets.keys():
            raise ValueError(f"There is no dataset with name '{dataset_name}'")

        full_path = os.path.join(local_filepath, local_filename)
        if os.path.exists(full_path) == False:
            raise ValueError(f"There is no such file '{full_path}'")

        with open(full_path, "rb") as fileIO:
            filebytes = bytearray(fileIO.read())

        self.add_file(dataset_name, filebytes, filled_md, local_filename, skip_values)
        return

    def add_file(
        self,
        dataset_name: str,
        filebytes: bytearray,
        filled_md: Dict[str, Any],
        filename: str,
        skip_values: bool = False,
    ):
        if dataset_name not in self.__datasets.keys():
            raise ValueError(f"There is no dataset with name '{dataset_name}'")

        catalogue = self.__dataset_cataloque_naming(dataset_name)
        if self.__driver.is_exist(filename, catalogue) == True:
            raise ValueError(
                f"There is already file with name '{filename}' in dataset '{dataset_name}'!"
            )

        self.__datasets[dataset_name].add_file_obj(
            filebytes, filename, filled_md, skip_values
        )
        return

    # pulling info
    def check_and_pull(self):
        pass

    # working with datasets method
    def create_dataset(
        self,
        new_dataset_name: str,
        datasets_descr: str,
        datasets_md_schema: Dict[str, str],
    ):
        if new_dataset_name in self.__datasets.keys():
            raise ValueError(f"There is already dataset with name '{new_dataset_name}'")

        datasets_cataloque = self.__dataset_cataloque_naming(new_dataset_name)
        self.__driver.create_cataloque(datasets_cataloque)
        new_dataset = Dataset()
        new_dataset.create_dataset(
            new_dataset_name,
            self.__driver,
            datasets_cataloque,
            datasets_descr,
            datasets_md_schema,
        )
        self.__datasets[new_dataset_name] = new_dataset
        self.save_state()
        return

    # TODO
    def merging_datasets(
        self,
        new_dataset_name: str,
        src_datasets_names: List[str],
        mapping_md: Dict[str, List[Callable]],
        new_md_table: Dict[str, str],
    ) -> bool:
        return

    def save_state(self):
        datasets_info = [
            {
                self.__DATALAKE_DATASET_NAME_FIELD: dn,
                self.__DATALAKE_DATASET_CATALOQUE_FIELD: self.__dataset_cataloque_naming(
                    dn
                ),
            }
            for dn in self.__datasets.keys()
        ]

        datalake_info_dict = {
            self.__DATALAKE_NAME_FIELD: self.__name,
            self.__DATALAKE_DESCR_FIELD: self.__descr,
            self.__DATALAKE_DATASETS_LIST_FIELD: datasets_info,
        }

        json_bytes = json.dumps(datalake_info_dict).encode("utf-8")
        byte_array = bytearray(json_bytes)
        self.__driver.write(byte_array, self.__DATALAKE_INFO_FN, self.__cataloque)
        return
