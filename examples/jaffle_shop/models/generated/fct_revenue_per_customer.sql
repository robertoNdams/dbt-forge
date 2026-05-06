{{ config(materialized='table') }}

select
    customer_id,
    sum(amount) as total_revenue,
    count(order_id) as n_orders
from {{ ref('stg_orders') }}
group by customer_id
having total_revenue > 100
order by
    total_revenue desc
