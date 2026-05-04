# MCAT Taxonomy Pipeline

An automated 14-agent orchestration pipeline to process MCAT taxonomy data from zipped files. 
It processes the provided catalogue inputs and produces structured `context.json` and `related_mcat_context.json` files.

## Project Structure

- `input/`: Place your input ZIP files here. Each zip represents a category to process.
- `output/`: Processed outputs are saved here, separated by ZIP filename.
- `_work/`: Temporary directory where ZIP files are extracted and intermediary files are kept.
- `pipeline/`: Core logic and orchestration.
  - `agents/`: Contains wave 0 to wave 3 agent logic.
  - `config.py`: Configuration details such as LLM models, API keys, and concurrency limits.
  - `orchestrator.py`: Controls the execution flow across all waves.
  - `preprocessor.py`: Pure Python tool to score candidates quickly.
- `run_pipeline.py`: The main entry point to run the pipeline.
- `SKILL-v6_3.md`: Specifications defining the pipeline steps, JSON structure, and rules.

## Prerequisites

- Python 3.10+
- The necessary requirements installed (e.g., `rapidfuzz`, `litellm` etc.).

## How to Run

1. **Place Input Data**: Add your target `.zip` file(s) into the `input/` directory. For example, `input/Inflatable Swimming Pool.zip`.
2. **Configure API Key**: In `pipeline/config.py`, ensure your `LITELLM_API_KEY` is properly set.
3. **Run Pipeline**:
   ```bash
   python3 run_pipeline.py
   ```
4. **Check Output**: Once complete, the output JSON files will be located in the `output/<zip_name>/` folder. A `token_usage_report.json` will also be generated there.

## Logic Flow

1. **Extract**: ZIPs from `input/` are extracted to `_work/`.
2. **Resolve**: Required CSV/Excel/PDF files are found.
3. **Preprocess**: Pure python scoring to reduce the number of candidate products.
4. **Agent Waves**:
    - **Wave 0**: Sequentially runs Agent 1 (PDF) & Agent 2 (Product Verification).
    - **Wave 1**: Runs Agent 3 (Context & Market extraction).
    - **Wave 2**: Parallel execution of Agents 4 through 11 for context features.
    - **Wave 3a/b**: Final naming and structural verdict.
    - **Wave 4 (Consolidator)**: Consolidates outputs to final valid JSON format.
