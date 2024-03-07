# WaterTAP Electrolyte Database (EDB)

## Getting started

### Installation

```sh
pip install git+https://github.com/watertap-org/electrolytedb
```

### Usage

```sh
edb --help
```

## Getting started (for contributors)

### Installation

```sh
git clone https://github.com/watertap-org/electrolytedb && cd electrolytedb
pip install -r requirements-dev.txt
```

### Running tests

```sh
pytest --pyargs electrolytedb --edb=mock
# requires mongod to be installed, e.g. conda install -c conda-forge mongodb
pytest --pyargs electrolytedb --edb=mongod
```
