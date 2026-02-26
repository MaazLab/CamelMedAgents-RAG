from query_reformulation.pipeline import LLMQueryProcessingPipeline

query = """
Hey so I've been kinda feeling weird lately,
my chest feels tight when I climb stairs
and I get really tired.
Not sure if it's serious.
"""

pipeline = LLMQueryProcessingPipeline()
result = pipeline.run(query)

print("result.keys(): ", result.keys())
print("Query: ", query)
for key in result.keys():
    print(f"\n--- {key} ---")
    print(result[key])