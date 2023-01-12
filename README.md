# VulChecker Pipeline

A deep learning system for detecting vulnerabilites (CWEs) in source code. 
The pipeline has been desinged to work on cmake C/C++ projects only.

# Using the Pipeline

## Setup

You will need to build [LLAP](https://github.gatech.edu/vulchecker/llap).
Follow the instructions there to build LLAP.
As a final step, collect all of the `vulchecker_*.so` files into a single directory.

Then, set up a virtual environment in which to run vulchecker.
Clone this repository and structure2vec:

```bash
git clone git@github.gatech.edu:vulchecker/vulchecker.git
git clone git@github.gatech.edu:vulchecker/structure2vec.git
```

Then, build a virtual environment and install all the components:

```bash
python3.7 -m venv vulchecker_env
. vulchecker_env/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install cython cmake
python -m pip install ./structure2vec ./vulchecker
```

After doing this the first time, you can simply

```bash
. vulchecker_env/bin/activate
```

to get a new shell ready to work.
This project exposes a command-line tool, `vulchecker`,
that is used for all operations.
There is built-in help,
which can be printed by passing the `--help` flag to any command or subcommand.
For example, `vulchecker --help` prints all of the available subcommands.

## Training a Model

### Labeling Programs

Labels for known vulernabilities are usually generated using ARCUS.
(TODO: What URL should I use to refer to ARCUS?)
Follow the instructions there to use ARCUS.

It's also possible to create labels by hand.
The labels file is a JSON array of objects.
Each object has three keys, `filename`, `line_number`, and `label`.
The recognized labels are:

CWE | Root Cause Label | Manifestation Label
--- | ---------------- | -------------------
121 (Stack Overflow) | `declared_buffer` | `stack_overflow`
122 (Heap Overflow) | `declared_buffer` | `heap_overflow`
190 (Integer Overflow | `overflowed_variable` | `overflowed_call`
191 (Integer Underflow | `underflowed_variable` | `underflowed_call`
415 (Double Free) | `first_free` | `second_free`
416 (Use After Free) | `freed_variable` | `use_after_free`

For example,
the labels file might contain:

```json
[
    {"filename": "src/foo.c", "line_number": 27, "label": "declared_buffer"},
    {"filename": "src/foo.c", "line_number": 37, "label": "stack_overflow"}
]
```

### Analyzing programs

Currently,
only C/C++ projects built using [CMake](https://cmake.org/) are supported.

Suppose you would normally build the executable to be analyzed like this:

```bash
mkdir build
cd build
cmake -GNinja ..
ninja foo
```

You can analyze this project with LLAP by running

```bash
vulchecker configure \
    --llap-lib-dir /path/to/llap/lib \
    --labels labels.json \
    cmake \
    foo \
    121 190 415 416
cd vulchecker_build
ninja -f vulchecker.ninja
```

This will produce files named `vulchecker-{121,190,415,416}.json`
containing the annotated PDGs for each pipeline.
These correspond to the *pipelines*, which may cover more than one CWE.

Pipeline | Covered CWES
-------- | ------------
121 | 121, 122
190 | 190, 191
415 | 415
416 | 416

These steps can be run concurrently by program.

### Augmenting Graphs

Optionally,
you can augment the PDGs extracted from the real world programs
with vulnerabilities taken from Juliet.
You will need the raw Juliet PDGs in a single file,
one per line.
For example, in `labeled-dataset`:

```bash
find CWE121/labeled_graphs -name '*.json' | xargs cat >juliet-121-pdgs.nljson
```

Then, you can augment a program like this:

```bash
vulchecker augmentation \
    --output vulchecker-121-augmented.json \
    juliet-121-pdgs.nljson \
    vulchecker-121.json
```

### Preprocessing Graphs

For eacn program, run

```bash
vulchecker preprocess \
    --training-indexes /path/to/indexes/indexes-121.json \
    --source-dir $PWD \
    --cwe 121 \
    --output vulchecker-121-preproc.json \
    vulchecker-121.json
```

Some pipelines correspond to more than one CWE.
In that case,
you'll need to make additional calls to `preprocess` for the additional CWEs.
For example, CWE-122:

```bash
vulchecker preprocess \
    --training-indexes /path/to/indexes/indexes-122.json \
    --source-dir $PWD \
    --cwe 122 \
    --output vulchecker-122-preproc.json \
    vulchecker-121.json
```

These steps can be run concurrently by CWE.
The preprocess script reads and writes the index file,
so all preprocessing for each CWE must be run serially.

### Gather Preprocessed Graphs

You need to gather the graphs for each CWE:

```bash
find . -name 'vulchecker-121-preproc.json' | xargs cat >real-world-121.nljson
```

and so on.

### Verify Data

Run

```bash
vulchecker validate_data \
    --check-labels \
    --output real-world-121-clean.nljson \
    real-world-121.nljson
```

This will warn you about any graphs with issues that will cause problems further along the pipeline.
The most common issue is that a program might not have any labeled nodes
even if there were labeled lines of source.
There are several reasons this may happen,
but they have to be investigated one at a time.
It outputs the good data.

### Train/Test Split

```bash
vulchecker train_test_split \
    --test-fraction 0.1 \
    real-world-121-clean.nljson \
    real-world-121-clean-train.nljson \
    real-world-121-clean-test.nljson
```

### Downsample Data

The data sets have a heavy class imbalance,
so we downsample the negative manifestation points.
This also helps with memory usage during the training step.
The downsampling script prints the final count of labels,
and I usually adjust the sampling rate until
the classes are approximately balanced.

```bash
vulchecker sample_data \
    --negative 0.00025 \
    real-world-121-clean-train.nljson \
    real-world-121-clean-0.00025-1.0-train.nljson
```

Output will be like:

```
{False: 123, True: 45}
```

### Train a Model

The basic command is

```bash
vulchecker train \
    --indexes /path/to/indexes/indexes-121.json \
    121 \
    real-world-121-model \
    real-world-121-clean-train.nljson \
    real-world-121-clean-test.nljson
```

but there are many options controlling the hyperparameters.
Run `vulchecker train --help` to see the available options.

The model is writetn into the directory `real-world-121-model` in this example.
This directory can exist, but, if it does, it must be empty.
The model serialization format consists of two files:
a PyTorch weights checkpoint,
and a metadata file with additional information needed to make predictions.

### Evaluate the Model

The `stats` subcommand computes basic statistics about the test set,
and writes more detailed information to disk.

```bash
vulchecker stats \
    --predictions-csv predictions-121.csv \
    --dump stats-121.npz \
    --roc-file roc-121.png \
    real-world-121-model \
    real-world-121-clean-test.nljson
```

### Make Predictions

Again, from the working directory of a project:

```bash
vulchecker lint \
    --llap-lib-dir /path/to/llap/lib \
    . \
    foo \
    real-world-121-model \
    real-world-122-model
```

By default,
output is written to standard output in a lint-like text format.
You can alternatively request CSV output by passing `--output-format csv`.
You can send the output to a file by passing `--output path/to/file`.

# Developer Quickstart

vulchecker depends on [NetworKit](https://networkit.github.io/),
which uses Cython but doesn't declare that according to PEP 518.
You must have Cython installed before attempting to resolve the NetworKit dependency.
We can work around this by pre-building wheels and
setting the `PIP_FIND_LINKS` environment variable:

```bash
for py_interp in python3.6 python3.7 python3.8; do
    $py_interp -m venv build-env
    . build-env/bin/activate
    python -m pip install -U pip setuptools wheel
    python -m pip install cython cmake
    python -m pip wheel -w wheelhouse networkit
    deactivate
    rm -rf build-env
done
export PIP_FIND_LINKS="$PWD/wheelhouse"
```

You will also need to add a wheel for
[`structure2vec`](https://github.gatech.edu/vulchecker/structure2vec)
to the `wheelhouse` directory.
Don't forget to set `PIP_FIND_LINKS` each time you start a new shell.

With the project cloned and a virtual environment active:

```bash
pip install -e .[dev,tests,docs]
```

You should configure [pre-commit](https://pre-commit.com/) to check your code before you commit:

```bash
pre-commit install
```

To run the tests, you will need all supported versions of Python installed.
On Ubuntu, you can use the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa).
In other places, you can use [pyenv](https://github.com/pyenv/pyenv).
You can run the automated tests by saying:

```bash
tox
```

# Performance Critical Code (Cython)

vulchecker uses [Cython](https://cython.org/) for performance-critical functions.
The Cython files are named `_foo.pyx`,
and should be imported in the corresponding `foo.py` file.
It's also OK to `cimport` the Cython objects from other Cython source files.

## Graphs to Matrices

When training models,
we discovered that it took a very long time to load the data into memory.
Profiling just the data loading part revealed that
converting the graphs to matrix representation was taking most of the time.
I therefore converted that code (`mean_field_from_node_link_data`) to Cython.

The `feature_row` function was taking up a plurality of the internal time of that function,
so I reduced the dynamism by creating a "compiled feature" Cython extension class
that remembers the number of columns for each feature
(I call this the feature's "width").
There's a concrete class for each feature kind,
so the dynamic dispatch into the individual handlers
becomes an indirect function call at the C level.

# Features

## Node Features

| Feature Name | Feature Identifier | Computed By | Comment |
| ------------ | ------------------ | ----------- | ------- |
| Static Value | `static_value` | | |
| Operation | `operation` | LLAP | |
| Basic Function | `function` | | name of function defined in other compilation unit |
| Output dtype | `dtype` | LLAP | |
| Part of "if" clause | `condition` | LLAP | |
| Number of data dependents | `def_use_out_degree` | vulchecker ML | |
| Number of control dependents | `control_flow_out_degree` | vulchecker ML | |
| Betweenness | `betweenness` | vulchecker ML | |
| Distance to manifestation point | `distance_manifestation` | vulchecker ML | |
| Distances to nearest root cause point | `distance_root_cause` | vulchecker ML | |
| Operation of nearest root cause point | `nearest_root_cause_op` | vulchecker ML | `call` or plurality or uniform random |
| Node tag | `tag` | LLAP | list-set of {`root_cause`, `manifestation`} |

## Node Metadata

| Metadata Description | Metadata Identifier |
| -------------------- | ------------------- |
| Containing function | `containing_function` |
| Source file | `file` |
| Source line | `line_number` |
| Training label | `label` |

## Edge Features

| Feature Name | Feature Identifier | Computed By | Comment |
| ------------ | ------------------ | ----------- | ------- |
| dtype | `dtype` | LLAP | |
| edge type | `type` | LLAP | |

# Input Graph Structure

Input should be in the node-link JSON format.
That looks like this:

``` json
{
    "graph": {},
    "nodes": [
        {
            "id": 0,

            "static_value": null,
            "operation": "add",
            "function": null,
            "dtype": "int64",
            "condition": false,
            "tag": [],
            "file": "foo.c",
            "line_number": 27,
            "containing_function": "foo",
            "label": "negative"
        }
    ],
    "links": [
        {
            "source": 0,
            "target": 0,

            "type": "def_use",
            "dtype": "int64"
        }
    ]
}
```

Every node needs a unique ID in order to match the edges to the nodes.
The unique ID has no semantic meaning,
and so you can simply assign sequential numbers.
The objects for `graph`, `nodes`, and `links` can contain arbitrary additional data.
Only the `id`, `source`, and `target` keys are reserved.

When processing unlabeled input, omit the `label` key from the node data.

I will compute the graph-structure features
(betweenness,
distance to manifestation,
distance to nearest root-cause,
operation of nearest root-cause)
in my code.

For categorical features,
I currently plan to pass over the data twice:
once to find out what all the possible values are,
and again to produce one-hot vectors of the appropriate size.
That means it doesn&rsquo;t matter what exact values are produced.

My code specially handles some categorical values.
It recognizes
`"tag": ["manifestation"]` and `"tag": ["root_cause"]`
for producing graph features.
It recognizes
`"operation": "call"`
for breaking ties on the operation of the nearest root cause.
If those aren&rsquo;t the most natural values,
I can swap them out for something else.

For ease of combining multiple outputs into a data set,
the JSON should be output in minified form;
specifically, it should be on a single line with a trailing newline.
