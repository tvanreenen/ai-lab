import os
from typing import Any

import logfire
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent, format_as_xml
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import IsInstance, LLMJudge

load_dotenv()

logfire.configure(
    token=os.getenv("LOGFIRE_WRITE_TOKEN"),
    send_to_logfire="if-token-present",
    service_name=os.path.basename(os.path.dirname(__file__)),
)

class CustomerOrder(BaseModel):
    dish_name: str
    dietary_restriction: str | None = None

class Recipe(BaseModel):
    ingredients: list[str]
    steps: list[str]

recipe_dataset = Dataset[CustomerOrder, Recipe, Any](
    cases=[
        Case(
            name="vegetarian_recipe",
            inputs=CustomerOrder(dish_name="Spaghetti Bolognese", dietary_restriction="vegetarian"),
            evaluators=(
                LLMJudge(rubric="Recipe should not contain meat or animal products"),
            ),
        ),
        Case(
            name="gluten_free_recipe_1",
            inputs=CustomerOrder(dish_name="Chocolate Cake", dietary_restriction="gluten-free"),
            evaluators=(
                LLMJudge(rubric="Recipe should not contain gluten or wheat products"),
            ),
        ),
        Case(
            name="gluten_free_recipe_2",
            inputs=CustomerOrder(dish_name="Pizza from Scratch", dietary_restriction="gluten-free"),
            evaluators=(
                LLMJudge(rubric="Recipe should not contain gluten or wheat products"),
            ),
        ),
        Case(
            name="tricky_gluten_free_recipe",
            inputs=CustomerOrder(dish_name="Shrimp Fried Rice", dietary_restriction="gluten-free"),
            evaluators=(
                LLMJudge(rubric="Recipe should not contain gluten or wheat products. Be careful to evaluate ingredients that are likely to contain gluten."),
            ),
        ),
    ],
    evaluators=[
        IsInstance(type_name="Recipe"),
        LLMJudge(rubric="Recipe should have clear steps and relevant ingredients"),
    ],
)

recipe_agent = Agent(
    "openai:gpt-4o",
    output_type=Recipe,
    instructions="Generate a recipe to cook the dish that meets the dietary restrictions.",
)

async def transform_recipe(customer_order: CustomerOrder) -> Recipe:
    r = await recipe_agent.run(format_as_xml(customer_order))
    return r.output

report = recipe_dataset.evaluate_sync(transform_recipe)
print(report)
