{{ config(materialized='table') }}

with
paid_high_value as (
    select
        customer_id,
        amount
    from {{ ref('stg_orders') }}
    where amount >= 50
)

select
    customer_id,
    sum(amount) as hv_revenue
from paid_high_value
group by customer_id
order by
    hv_revenue desc
