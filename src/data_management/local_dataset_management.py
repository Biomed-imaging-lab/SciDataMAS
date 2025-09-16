from copy import deepcopy
from datetime import datetime
import json
import os
import shutil
from typing import Any, Callable, Dict, List, Optional, Set, Union

import pandas as pd
from pandasql import sqldf
import numpy as np


class LocalRichDataset:
    """
    LocalRichDataset class for describing local storaged rich datasets.

    'Local storaged rich datasets' - is a dataset, placed on some local hard drive, which stores not only files of a dataset, but a useful
    metadata, which makes data more interpretable and reusable.

    Useful metadata fields are also manageble by this class (it's bad - should be some independet class which provides this type of work),
    the management is driven by created in research rules, which makes metadata adaptive for variative vectores of researching.

    The main three blocks of meta:
    - basic (main) properties: author, path_to_file, id, adding_date
    - properties before capturing: these properties are descibing different aspects of researching object -
        what is the object, his properties, properties of enviroment (experiment), properties of registering device and so on.
        If the data is software generated: this block describes arguments and code of software.
        If the data is external - this block describes source and already created meta.
    - properties after capturing: these block is a fancy changable area of fields for researching. Researches can add fields, edit them, fill
        with useful for them data - all for making bigger and useful ontology of some data for current vectir of researching.
    """

    __INFO_FILENAME = "datalake_info.json"
    __METADATA_DF_NAME = "metadata.csv"
    __DATA_DIRECTORY = "data"

    __PATH_MD_FIELD = "path"
    __DATE_MD_FIELD = "added_date"
    __ID_COLUMN_FIELD = "id"

    __META_DESCR_NAME = "descr"
    __META_TYPE_NAME = "type"

    # initialization instances block
    def __init__(
        self,
        path: str,
        name: str,
        descr: str,
        pre_capturing_metadata_schema: Dict[str, Dict[str, str]],
        post_capturing_metadata_schema: Dict[str, Dict[str, str]] = {},
        depricated_pre_meta_fields: Set[str] = (),
    ):

        # base main info
        self.name = name
        self.descr = descr
        self.placement_path = path

        # rich data info format
        self.__pre_capturing_metadata_schema = pre_capturing_metadata_schema
        self.__post_capturing_metadata_schema = post_capturing_metadata_schema

        # some additional fields for management and higher quality management
        # self.__common_pre_meta_fields_with_values = common_pre_meta_fields_with_values
        self.__depricated_pre_meta_fields = depricated_pre_meta_fields

        # read df for further working with
        self.__metadata_df = pd.read_csv(
            os.path.join(self.placement_path, LocalRichDataset.__METADATA_DF_NAME)
        )
        self.__metadata_df.set_index(LocalRichDataset.__ID_COLUMN_FIELD, inplace=True)

        type_mapper = {
            "int": np.int64,
            "float": np.float64,
            "categorical": "category",
            "bool": np.bool_,
            "date": "datetime64[ns]",
        }
        passed_types_mapping = {
            key: type_mapper.get(
                elem[LocalRichDataset.__META_TYPE_NAME],
                "object",
            )
            for key, elem in self.__pre_capturing_metadata_schema.items()
        }

        self.__metadata_df.astype(passed_types_mapping)

        return

    @staticmethod
    def read(path: str):
        """
        Static method for reading existing local rich dataset
        """
        # 0 - checking of path and file description existing
        if not os.path.exists(path):
            raise FileNotFoundError(f"The '{path}' doesn't leads to anything!")
        if os.path.isfile(path):
            raise ValueError(
                "The path '{path}' leads to a file, not to a folder with a dataset!"
            )
        info_path = os.path.join(path, LocalRichDataset.__INFO_FILENAME)
        if not os.path.exists(info_path):
            raise ValueError(f"The info file about datalake doesn't found in '{path}'")
        metadata_df = os.path.join(path, LocalRichDataset.__METADATA_DF_NAME)
        if not os.path.exists(metadata_df):
            raise ValueError(f"The file with metadata doesn't found in '{path}'")

        # 1 - read data
        with open(info_path, "r") as i_stream:
            json_dict = json.load(i_stream)

        # 2 - generate instance of LocalRichDataset
        local_rich_dataset = LocalRichDataset(
            json_dict["local_datalake_path"],
            json_dict["name"],
            json_dict["description"],
            json_dict["pre_capturing_md"],
            json_dict["post_capturing_md"],
            json_dict["depricated_pre_capturing_md_fields"],
        )
        return local_rich_dataset

    def get_path(self) -> str:
        return self.placement_path

    @staticmethod
    def create(
        folder_path: str,
        name: str,
        descr: str,
        pre_capturing_metadata_schema: Dict[str, Dict[str, str]],
    ):
        # 0 - make all checks
        if not os.path.exists(folder_path):
            raise FileNotFoundError(
                f"The dataset can't be saved into '{folder_path}' path: folder doesn't exists!"
            )
        if os.path.isfile(folder_path):
            raise ValueError(f"The path '{folder_path}' leads to a file, not a folder!")

        full_dataset_path = os.path.join(folder_path, name)
        if os.path.exists(full_dataset_path):
            raise FileExistsError(
                f"Can't create new dataset in '{folder_path}' with name '{name}': the folder with name is already exists!"
            )

        # 1 - generate instance
        os.mkdir(full_dataset_path)
        os.mkdir(os.path.join(full_dataset_path, LocalRichDataset.__DATA_DIRECTORY))
        column_names = [
            LocalRichDataset.__ID_COLUMN_FIELD,
            LocalRichDataset.__PATH_MD_FIELD,
            LocalRichDataset.__DATE_MD_FIELD,
            *list(pre_capturing_metadata_schema.keys()),
        ]

        # 2 - format with types dataframe
        df = pd.DataFrame(columns=column_names)
        df.set_index(LocalRichDataset.__ID_COLUMN_FIELD, inplace=True)
        df.to_csv(
            os.path.join(full_dataset_path, LocalRichDataset.__METADATA_DF_NAME),
        )

        type_mapper = {
            "int": np.int64,
            "float": np.float64,
            "categorical": "category",
            "bool": np.bool_,
            "date": "datetime64[ns]",
        }
        passed_types_mapping = {
            key: type_mapper.get(
                elem[LocalRichDataset.__META_TYPE_NAME],
                "object",
            )
            for key, elem in pre_capturing_metadata_schema.items()
        }

        df.astype(passed_types_mapping)

        # 3 - generate instance
        new_rich_dataset = LocalRichDataset(
            full_dataset_path, name, descr, pre_capturing_metadata_schema
        )

        # 4 - save it
        new_rich_dataset.save_datalake()
        return new_rich_dataset

    # logging datalake in file system block
    def __generating_dict_of_primary_info(self) -> Dict[str, Any]:
        info_dict = {
            "name": self.name,
            "description": self.descr,
            "local_datalake_path": self.placement_path,
            "pre_capturing_md": self.__pre_capturing_metadata_schema,
            "post_capturing_md": self.__post_capturing_metadata_schema,
            "depricated_pre_capturing_md_fields": self.__depricated_pre_meta_fields,
        }

        return info_dict

    def save_datalake(self):
        # 0 - save info about main structure
        file_info_full_path = os.path.join(
            self.placement_path, LocalRichDataset.__INFO_FILENAME
        )
        with open(file_info_full_path, "w") as o_file:
            json.dump(
                self.__generating_dict_of_primary_info(), o_file, ensure_ascii=False
            )

        # 1 - save df file
        self.__metadata_df.to_csv(
            os.path.join(self.placement_path, LocalRichDataset.__METADATA_DF_NAME)
        )
        return

    # reading datalake info methods block
    def get_string_base_info(self):
        result = f'Name: "{self.name}".\nDesciption: {self.descr}'
        return result

    # Working with metadata schema
    # - Reading schema
    def get_metadata_schema_for_filling(self, with_depricated_fields: bool = False):
        keys = list(self.__pre_capturing_metadata_schema.keys())

        if with_depricated_fields == False:
            keys = list(set(keys()) - self.__depricated_pre_meta_fields)

        dict_for_filling = {key: None for key in keys}
        return dict_for_filling

    def get_metadata_schema_rich_info(self, with_depricated_fields: bool = False):
        result_dict = self.__pre_capturing_metadata_schema
        result_dict.update(self.__post_capturing_metadata_schema)

        if with_depricated_fields == False:
            for elem in self.__depricated_pre_meta_fields:
                result_dict.pop(elem)

        return result_dict

    # Working with elements (add data, get data, add properties to some data)
    def add_data(
        self,
        data_metadata: Dict[str, Any],
        paths_for_data: Union[str, List[str]],
        allow_none_values: bool = False,
        register_new_post_capt_props: bool = False,
    ):
        """
        Adding new data in datalake with filled pre-capturing and some post-capturing properties
        """

        # 0 - test metadata filling section
        for key in self.__pre_capturing_metadata_schema:
            if (key in data_metadata.keys() == False) and (
                key in self.__depricated_pre_meta_fields == False
            ):
                raise ValueError(
                    f"Key '{key}' is not passed in dictionary and it is not depricated!"
                )
            if (
                (key in data_metadata.keys())
                and data_metadata[key] == None
                and allow_none_values == False
            ):
                raise ValueError(
                    f"Passed field '{key}' in metadata has 'None' value! Fill the gap (or add with 'allow_none_values=True' flag)."
                )

        new_fields = list(
            set(data_metadata.keys())
            - set(self.__pre_capturing_metadata_schema.keys())
            - set(self.__post_capturing_metadata_schema.keys())
        )

        if len(new_fields) > 0 and register_new_post_capt_props == False:
            raise ValueError(
                f"Passed metadata contains more fields than expected: can't save them as post capturing properies without 'register_new_post_capt_props=True' permission."
            )

        # 1.1 - copying data in 'local dataset'
        # 1.1.1 - unwarp paths for dir to list of files in it
        adding_date = datetime.now()

        tmp_paths = paths_for_data
        if isinstance(paths_for_data, str) == True:
            tmp_paths = [paths_for_data]

        paths = []
        for path in tmp_paths:
            if os.path.isdir(path):
                for item in os.listdir(path):
                    item_full_path = os.path.join(path, item)
                    if os.path.isfile(item_full_path):
                        paths.append(item_full_path)
            else:
                paths.append(path)

        folder_with_data_destination = os.path.join(
            self.placement_path, LocalRichDataset.__DATA_DIRECTORY
        )
        new_records = []
        for i, path in enumerate(paths):
            shutil.copy2(path, folder_with_data_destination)

            new_path = os.path.join(
                folder_with_data_destination, os.path.basename(path)
            )
            new_row_dict = deepcopy(data_metadata)
            new_row_dict.update(
                {
                    LocalRichDataset.__ID_COLUMN_FIELD: len(self.__metadata_df.index)
                    + i,
                    LocalRichDataset.__PATH_MD_FIELD: new_path,
                    LocalRichDataset.__DATE_MD_FIELD: adding_date,
                }
            )
            new_records.append(new_row_dict)

        new_row_dict_df = pd.DataFrame.from_records(new_records, index="id")

        # 1.2 - register data in pandas dataframe
        self.__metadata_df = pd.concat([self.__metadata_df, new_row_dict_df])

        # 1.3 - update csv in local storage
        self.__metadata_df.to_csv(
            os.path.join(self.placement_path, LocalRichDataset.__METADATA_DF_NAME)
        )
        return

    def get_elements_by_sql_request(self, sql_request: str) -> pd.DataFrame:
        """
        Getting elements info (df part) from datalake by passed sql request
        """

        df = self.__metadata_df
        result_df = sqldf(sql_request, locals())
        return result_df

    def get_elements_by_df_criteria(self, criteria):
        """
        Getting elements info (df part) from datalake by passed dataframe criteria (some predicate)
        """
        return

    # getters block
    def get_metadata_df(self):
        return self.__metadata_df

    def get_pre_capturing_fields(self):
        return self.__pre_capturing_metadata_schema
