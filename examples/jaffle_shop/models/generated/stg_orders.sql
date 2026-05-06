{{ config(materialized='view') }}

select
    id as order_id,
    user_id as customer_id,
    order_date,
    amount
from {{ source('raw', 'orders') }}
where status != 'cancelled'
