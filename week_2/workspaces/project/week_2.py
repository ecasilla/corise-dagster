from datetime import datetime
from typing import List

from dagster import (
    In,
    Nothing,
    OpExecutionContext,
    Out,
    ResourceDefinition,
    String,
    graph,
    op,
)
from workspaces.config import REDIS, S3, S3_FILE
from workspaces.resources import mock_s3_resource, redis_resource, s3_resource
from workspaces.types import Aggregation, Stock
from operator import attrgetter


@op(
    config_schema={"s3_key": String},
    required_resource_keys={"s3"},
    tags={"kind": "s3"},
    out={"stocks": Out(dagster_type=List[Stock])},
)
def get_s3_data(context: OpExecutionContext) -> List[Stock]:
    s3 = context.resources.s3
    stock_strings = s3.get_data(context.op_config["s3_key"])
    return list(map(Stock.from_list, stock_strings))


@op(
    ins={"stocks": In(dagster_type=List[Stock])},
    out={"aggregation": Out(dagster_type=Aggregation)},
    description="Return the Aggregation with the highest stock price",
)
def process_data(context, stocks) -> Aggregation:
    highest_stock = max(stocks, key=attrgetter("high"))
    return Aggregation(date=highest_stock.date, high=highest_stock.high)


@op(
    required_resource_keys={"redis"},
    tags={"kind": "redis"},
    ins={"aggregation": In(dagster_type=Aggregation)},
    out=Out(Nothing),
    description="Upload an Aggregation to Redis",
)
def put_redis_data(context, aggregation):
    redis = context.resources.redis
    redis.put_data(  
        name=String(aggregation.date),
        value=String(aggregation.high)
    )


@op(
    required_resource_keys={"s3"},
    tags={"kind": "s3"}, 
    ins={"aggregation": In(dagster_type=Aggregation)},
    out=Out(Nothing),
)
def put_s3_data(context, aggregation):
    s3 = context.resources.s3
    s3.put_data(
        name=String(aggregation.date),
        data=aggregation
    )


@graph
def machine_learning_graph():
    stocks = get_s3_data()
    aggregation = process_data(stocks)
    put_redis_data(aggregation)
    put_s3_data(aggregation)


local = {
    "ops": {"get_s3_data": {"config": {"s3_key": S3_FILE}}},
}

docker = {
    "resources": {
        "s3": {"config": S3},
        "redis": {"config": REDIS},
    },
    "ops": {"get_s3_data": {"config": {"s3_key": S3_FILE}}},
}

machine_learning_job_local = machine_learning_graph.to_job(
    name="machine_learning_job_local",
    config = local,
    resource_defs={
        "s3": mock_s3_resource,
        "redis": ResourceDefinition.mock_resource()
    }
)

machine_learning_job_docker = machine_learning_graph.to_job(
    name="machine_learning_job_docker",
    config=docker,
    resource_defs={
        "s3": s3_resource,
        "redis": redis_resource
    }
)
