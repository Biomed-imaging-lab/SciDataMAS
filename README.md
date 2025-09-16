# SciDataMAS: LLM-Driven MAS for Scientific Data Management

## Project Description

**SciDataMAS** is a project aimed at creating a Multi-Agent System (MAS) for moderating and describing complex scientific data.

### Goals

1)  Aggregate and provide a comprehensive description with metadata for incoming scientific data from various sources, ensuring the openness, transparency, and interpretability of the obtained data;
    -   Data is aggregated based on its origin (e.g., by the same format of preparing real samples) and modalities;
    -   The data description format is generated based on the process description obtained from an LLM, followed by human moderation;
    -   When adding new data, the required metadata fields are filled in either (by the system or user).
2)  Search for required data using natural language queries;


## Instalation and guides

#### 1. Cloning repo.

First of all, you need to clone this repo. You can do it with URL (ssh), which are showes up when you click on 'Code' button above and next command:

```
git clone *https/ssh key of repo*
```

#### 2. Creating virtual environment.

Next, open terminal in repository directory, wehre stored all demos, code and 'requirements.txt' file to make new environment. 


Be sure that you installed Python3 and upgraded pip before!

To create environment and install dependencies, make next commands:

```
python3 -m venv ./.venv
source ./.venv/bin/activate
pip install -r requirements.txt
```

#### 3. Filling ".env" file for models.

To use this MAS, it is important to create ".env" file with environment variables with API keys. It should contains different keys and looks something like this:
```
MISTRAL_API_KEY=*some_key*
OPENAI_API_KEY=*some_key*
```

Also, it is useful to have keys for langsmith because it's provides free opporunities to monitor MAS workflow's execution traces.

Now, you are ready to use the SciDataMAS. But, firstly, check out next demos.

#### 4. Checking demos for understanding use cases.

Here are all demos:
1)  Working with local data lake: [click](./mas_demonstration/local_science_datalake_demo.ipynb);
2)  Creating metadata tables: [click](./mas_demonstration/creating_dataset_demo.ipynb);
3)  Adding data to data lake: [click](./mas_demonstration/adding_data_demo.ipynb);
4)  Getting data from data lake: [click](./mas_demonstration/getting_data_demo.ipynb);
5)  Working with MAS (and adding tools to MAS for working with data): [click](./mas_demonstration/whole_mas_working_demo.ipynb).


## Testing

### Testing environment

- Python: 3.10.12;
- Models: GPT-5-mini, Mistral-medium-2508, GPT-4o (all testing was complited using API).

The mean and standart deviation was calculated on 16 runs of different experiments.

### 1. Creating metadata tables

| Model | Fields generated | Non-string fields |  Tokens (10^{3}) | Time (sec) |
|-------------|-------------|-------------|-------------|-------------|
| GPT-4o    | 18.8±2.9     | 10.3±2.4    | **4.3±0.3**   | **27.7±6**    |
| GPT-5-mini| **70.5±18.6**    | **39.8±11**     | 17±1.1    | 151±32    |
| Mistral   | 44.8±14.9    | 28.43±10    | 10.8±4    | 45±16     |

### 2. Automatic metadata filling during data insertion

| Model | Fields generated | Non-string fields |  Tokens (10^{3}) | Time (sec) |
|-------------|-------------|-------------|-------------|-------------|
| GPT-4o    | **10.9±1.9**  | **1.1±1.9**  | **11.7±2**  | 34±7.8    |
| GPT-5-mini| 10.3±2    | 2.1±2    | 17±3    | 139±111   |
| Mistral   | 8.8±1.8   | 3.5±1.8  | 23±7.8  | **30±3.8**    |

## Key points of such project:
-   [x] (Through trial and error) Implement the most suitable MAS structure for working with data through tools;
-   [x] Illustrate the architecture of the MAS element for data processing (for the article) in drawio, upload to the docs;
-   [x] Testing MAS on various scenarios;
-   [x] Prepare repo and text for AAAI-26 student abstract track;
-   [x] Make demos and guides for other users.