import os
import json
from typing import Optional, Any
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# --- THE LATEST LANGCHAIN IMPORTS ---
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Observability / Logging
from langfuse.langchain import CallbackHandler
from langfuse import observe

# Assuming wrapper.py exists in your directory
from wrapper import log_async_exceptions 

load_dotenv()

# Initialize Langfuse CallbackHandler for Langchain (tracing)
langfuse_handler = CallbackHandler()

def get_latest_gemini_llm(model_type: Optional[str] = None) -> ChatGoogleGenerativeAI:
    """Returns the latest LangChain-compatible Gemini model using the unified SDK."""
    model_name = "gemini-3-flash-preview" # Default
    
    if model_type == "pro":  
        model_name = "gemini-3.1-pro-preview"
    elif model_type == "flash":  
        model_name = "gemini-3-flash-preview"
    elif model_type == "flash-lite":  
        model_name = "gemini-3.1-flash-lite-preview"

    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=1.0
    )

class LlmChain:
    def __init__(self, model_type: Optional[str] = None):
        # Initialize the LangChain LLM object
        self.llm = get_latest_gemini_llm(model_type)
        
    @log_async_exceptions
    async def aexecute_chain(
        self,
        prompt_template: str,
        input_vars: dict,
        parser: Optional[BaseModel] = None,
    ):
        if parser:
            parser_inst = JsonOutputParser(pydantic_object=parser)
            prompt_template += "\n {format_instructions} "
            partial_vars = {"format_instructions": parser_inst.get_format_instructions()}
        else:
            partial_vars = {}

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=list(input_vars.keys()),
            partial_variables=partial_vars
        )

        # Build the chain
        if parser:
            chain = prompt | self.llm | parser_inst
        else:
            chain = prompt | self.llm | StrOutputParser()
        
        # Retry logic
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                output = await chain.ainvoke(
                    input_vars,
                    config={"callbacks": [langfuse_handler]}
                )
                return output
            except (ValidationError, json.JSONDecodeError) as e:
                if attempt < max_attempts - 1:
                    print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                    continue
                else:
                    print(f"All {max_attempts} attempts failed. Raising error.")
                    raise

    @observe()
    def execute_chain(
        self, 
        prompt_template: str, 
        input_vars: dict, 
        parser: Optional[BaseModel] = None
    ):        
        if parser:
            parser_inst = JsonOutputParser(pydantic_object=parser)
            prompt_template += "\n {format_instructions} "
            partial_vars = {"format_instructions": parser_inst.get_format_instructions()}
        else:
            partial_vars = {}

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=list(input_vars.keys()),
            partial_variables=partial_vars
        )
        
        if parser:
            chain = prompt | self.llm | parser_inst
        else:
            chain = prompt | self.llm | StrOutputParser()
            
        response = chain.invoke(input_vars, config={"callbacks": [langfuse_handler]})
        
        return response

def init_gemini_embeddings(**kwargs: Any) -> GoogleGenerativeAIEmbeddings:
    # 💡 LATEST SETUP: Also updated to use the unified GenAI package
    model_name = kwargs.pop("model_name", "gemini-embedding-2-preview") 
    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        **kwargs
    )

