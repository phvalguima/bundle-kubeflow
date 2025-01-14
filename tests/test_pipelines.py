from typing import Callable

import pytest
from kfp import Client

from .pipelines.cowsay import cowsay_pipeline
from .pipelines.mnist import mnist_pipeline


COWSAY_PARAMS = [{"name": "url", "value": "https://helloacm.com/api/fortune/"}]


MNIST_PARAMS = [
    {'name': 'storage-endpoint', 'value': 'minio:9000'},
    {
        'name': 'test-images',
        'value': 'https://people.canonical.com/~knkski/t10k-images-idx3-ubyte.gz',
    },
    {
        'name': 'test-labels',
        'value': 'https://people.canonical.com/~knkski/t10k-labels-idx1-ubyte.gz',
    },
    {'name': 'train-batch-size', 'value': '128'},
    {'name': 'train-epochs', 'value': '2'},
    {
        'name': 'train-images',
        'value': 'https://people.canonical.com/~knkski/train-images-idx3-ubyte.gz',
    },
    {
        'name': 'train-labels',
        'value': 'https://people.canonical.com/~knkski/train-labels-idx1-ubyte.gz',
    },
]


@pytest.mark.parametrize(
    'name,params,fn',
    [('mnist', MNIST_PARAMS, mnist_pipeline), ('cowsay', COWSAY_PARAMS, cowsay_pipeline)],
)
def test_pipelines(name: str, params: list, fn: Callable):
    """Runs each pipeline that it's been parameterized for, and waits for it to succeed."""

    client = Client('127.0.0.1:8888')
    run = client.create_run_from_pipeline_func(
        fn, arguments={p['name']: p['value'] for p in params}
    )
    completed = client.wait_for_run_completion(run.run_id, timeout=1200)
    status = completed.to_dict()['run']['status']
    assert status == 'Succeeded', f'Pipeline status is {status}'
