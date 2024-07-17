from abc import ABC, abstractmethod
from typing import List
from src.data_storage import DataStorage
from src.llm import LLM

class SourceProcessor(ABC):
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.llm = LLM()

    def process(self, queries: List[str], sources_per_query: int, questions: List[str], max_outputs_per_platform=7) -> DataStorage:
        combined_data = self.combine_multiple_queries(queries, sources_per_query)
        data_with_content, data_witout_content = self.check_source_content(combined_data)
        tagged_data = self.add_smart_tags(data_with_content, questions)
        filtered_data = self.filter_relevant_sources(tagged_data)
        sorted_data = self.rank_sources_by_relevance(filtered_data)
        top_data, rejected_data = self.choose_top_sources(sorted_data, max_outputs_per_platform)
        return top_data, data_witout_content, rejected_data
    
    def combine_multiple_queries(self, queries: List[str], sources_per_query: int) -> DataStorage:
        combined_storage = DataStorage()
        for query in queries:
            query_storage = self.process_query(query, sources_per_query)
            combined_storage.combine(query_storage)
        return combined_storage
    
    def process_query(self, query: str, num_top_sources: int) -> DataStorage:
        sources = self.fetch_source_items(query, 2 * num_top_sources)
        filtered_sources = self.filter_low_quality_sources(sources)
        top_sources = self.select_top_sources(filtered_sources, num_top_sources)
        data_storage = self.collect_source_details_to_data_storage(top_sources)
        return data_storage
    
    @abstractmethod
    def fetch_source_items(self, query: str, limit: int) -> List[dict]:
        pass
    
    @abstractmethod
    def filter_low_quality_sources(self, sources: List[dict]) -> List[dict]:
        pass
    
    def select_top_sources(self, sources: List[dict], num_top_sources: int) -> List[dict]:
        return sources[:num_top_sources]
    
    @abstractmethod
    def collect_source_details_to_data_storage(self, sources: List[dict]) -> DataStorage:
        pass

    @abstractmethod
    def fetch_detailed_content(self, identifier: str) -> str:
        pass

    def add_smart_tags(self, data_storage: DataStorage, questions: List[str]) -> DataStorage:
        for platform_name in data_storage.data.keys():
            for title in data_storage.data[platform_name].keys():
                content = data_storage.data[platform_name][title].get("content")
                if not content:
                    continue
                
                if isinstance(content, dict):
                    content = "\n".join([f"{chapter}: {', '.join(lectures)}" for chapter, lectures in content.items()])

                summary, combine_flag = self.llm.summarize(content)

                if combine_flag:
                    combined_summary = self.llm.organize_summarization_into_one(summary)
                    data_storage.data[platform_name][title]["detailed_summary"] = summary
                    data_storage.data[platform_name][title]["summary"] = combined_summary
                else:
                    data_storage.data[platform_name][title]["summary"] = summary

                relevance_score = 0
                for question in questions:
                    answer = self.llm.ask_llama_question(question, content, summary)
                    if self.llm.validate_with_q_and_a_relevance(question, answer) and self.llm.validate_with_llm_knowledge(question, answer):
                        if "Q&A" not in data_storage.data[platform_name][title]:
                            data_storage.data[platform_name][title]["Q&A"] = {}
                        data_storage.data[platform_name][title]["Q&A"][question] = answer
                        relevance_score += 1
                
                data_storage.data[platform_name][title]["relevance_score"] = relevance_score
        return data_storage

    def filter_relevant_sources(self, data_storage: DataStorage) -> DataStorage:
        filtered_data = {}
        for platform_name, titles in data_storage.data.items():
            filtered_titles = {title: info for title, info in titles.items() if info.get("relevance_score", 0) > 0}
            if filtered_titles:
                filtered_data[platform_name] = filtered_titles
        data_storage.data = filtered_data
        return data_storage

    def rank_sources_by_relevance(self, data_storage: DataStorage) -> DataStorage:
        sorted_data = {}
        for platform_name, titles in data_storage.data.items():
            sorted_titles = dict(sorted(titles.items(), key=lambda item: item[1].get("relevance_score", 0), reverse=True))
            for title in sorted_titles:
                sorted_titles[title].pop("relevance_score", None)
            sorted_data[platform_name] = sorted_titles
        data_storage.data = sorted_data
        return data_storage
    
    def choose_top_sources(self, data_storage: DataStorage, max_outputs_per_platform: int):
        top_data = DataStorage()
        rejected_data = DataStorage()
        for platform_name, titles in data_storage.data.items():
            for title in titles.keys():
                if len(top_data.data.get(platform_name, {})) < max_outputs_per_platform:
                    top_data.add_data(platform_name, title, **titles[title])
                else:
                    rejected_data.add_data(platform_name, title, **titles[title])
        return top_data, rejected_data

    def check_source_content(self, data_storage: DataStorage):
        data_with_content = DataStorage()
        data_witout_content = DataStorage()
        for platform_name, titles in data_storage.data.items():
            for title, details in titles.items():
                content = details.get("content")
                if content:
                    data_with_content.add_data(platform_name, title, **titles[title])
                else:
                    data_witout_content.add_data(platform_name, title, **titles[title])
        return data_with_content, data_witout_content