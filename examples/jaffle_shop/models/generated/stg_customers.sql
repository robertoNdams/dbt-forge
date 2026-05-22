{{ config(materialized='view') }}

select
    id as customer_id,
    first_name,
    last_name,
    email
from {{ source('raw', 'customers') }}
