import json
import os
from dotenv import load_dotenv
from typing import Dict

import streamlit as st

from streamlit_gui import StreamlitGUI
from mas_exec.mas_exec import MASExec
from app_model import AppModel


class Session:
    ### vars
    __view: StreamlitGUI = None
    __mas: MASExec = None
    __model: AppModel = None

    ### const
    __CONFIG_PATH: str = "./conf.json"
    __MODEL_CONF_FIELD: str = "app_model_conf"
    __MAS_CONF_FIELD: str = "mas_conf"

    def __init_model(self):
        # read conf
        if not (
            os.path.exists(self.__CONFIG_PATH) and os.path.isfile(self.__CONFIG_PATH)
        ):
            raise RuntimeError(f"There is no '{self.__CONFIG_PATH}' conf file!")

        with open(self.__CONFIG_PATH, "rt") as conf_file:
            dict_conf = json.load(conf_file)

        # init app model
        if self.__MODEL_CONF_FIELD not in dict_conf.keys():
            raise RuntimeError(
                f"There is no '{self.__MODEL_CONF_FIELD}' config in file!"
            )

        return AppModel(dict_conf[self.__MODEL_CONF_FIELD])

    def __init_mas(self):
        # read conf
        if not (
            os.path.exists(self.__CONFIG_PATH) and os.path.isfile(self.__CONFIG_PATH)
        ):
            raise RuntimeError(f"There is no '{self.__CONFIG_PATH}' conf file!")

        with open(self.__CONFIG_PATH, "rt") as conf_file:
            dict_conf = json.load(conf_file)

        # init app model
        if self.__MAS_CONF_FIELD not in dict_conf.keys():
            raise RuntimeError(f"There is no '{self.__MAS_CONF_FIELD}' config in file!")

        return MASExec(dict_conf[self.__MAS_CONF_FIELD], self.__model)

    def __init_view(self):
        return StreamlitGUI(self.__mas)

    def __init__(self):
        if "app_model" not in st.session_state:
            app_model = self.__init_model()
            st.session_state["app_model"] = app_model
        self.__model = st.session_state["app_model"]

        if "mas" not in st.session_state:
            mas = self.__init_mas()
            st.session_state["mas"] = mas
        self.__mas = st.session_state["mas"]

        if "view" not in st.session_state:
            view = self.__init_view()
            st.session_state["view"] = view
        self.__view = st.session_state["view"]
        return

    def run(self):
        self.__view.run()
        return


if __name__ == "__main__":
    load_dotenv()
    session = Session()
    session.run()
