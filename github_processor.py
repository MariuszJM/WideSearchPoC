import requests
import base64
from typing import List
from data_storage import DataStorage
from base_processor import SourceProcessor
from config import GITHUB_TOKEN
from LLMProcessor import LLMProcessor

class GitHubProcessor(SourceProcessor):
    BASE_URL = "https://api.github.com/search/repositories"
    README_URL_TEMPLATE = "https://api.github.com/repos/{repo_full_name}/readme"

    def __init__(self, platform_name="GitHub"):
        self.platform_name = platform_name
        self.llm_processor = LLMProcessor()

    def combine_multiple_queries(
        self, queries: List[str], num_sources_per_query: int
    ) -> DataStorage:
        combined_storage = DataStorage()
        for query in queries:
            query_storage = self.process_query(query, num_sources_per_query)
            combined_storage.combine(query_storage)
        combined_storage = self.add_summary_info(combined_storage)
        return combined_storage

    def process_query(self, query: str, num_top_sources: int) -> DataStorage:
        response = self.search(query, num_top_sources)
        if response is None:
            return DataStorage()

        repositories = response["items"][:num_top_sources]

        top_data_storage = DataStorage()
        for repo in repositories:
            repo_info = self.get_repo_info(repo)
            readme_content = self.get_readme_content(repo["full_name"])
            repo_info["details"] = readme_content
            top_data_storage.add_data(self.platform_name, repo["full_name"], **repo_info)

        return top_data_storage

    def search(self, query: str, max_results):
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": max_results,
        }
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {GITHUB_TOKEN}"
        }

        response = requests.get(self.BASE_URL, params=params, headers=headers)

        if response.status_code != 200:
            print(f"Failed to retrieve repositories: {response.status_code}")
            return None
        return response.json()

    def get_repo_info(self, repo):
        return {
            "url": repo["html_url"],
            "description": repo["description"],
            "language": repo["language"],
        }

    def get_readme_content(self, repo_full_name):
        url = self.README_URL_TEMPLATE.format(repo_full_name=repo_full_name)
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            readme_info = response.json()
            readme_base64 = readme_info['content']
            readme_content = base64.b64decode(readme_base64).decode('utf-8')
            return readme_content
        else:
            print(f"Failed to fetch README for {repo_full_name}. Status code: {response.status_code}")
            return ""

    def add_summary_info(self, data_storage: DataStorage) -> DataStorage:
        for repo_full_name in data_storage.data[self.platform_name].keys():
            readme_content = self.get_readme_content(repo_full_name)
            summary = self.llm_processor.summarize_readme(readme_content)
            data_storage.data[self.platform_name][repo_full_name]["summary"] = summary

            # Process list of questions
            questions = ["Does the project support Docker?"]
            for question in questions:
                answer = self.llm_processor.ask_llama_question(question, readme_content, summary)
                if "Q&A" not in data_storage.data[self.platform_name][repo_full_name]:
                    data_storage.data[self.platform_name][repo_full_name]["Q&A"] = {}
                data_storage.data[self.platform_name][repo_full_name]["Q&A"][question] = answer

        return data_storage


if __name__ == "__main__":
    queries = ["Open Web UI"]
    github_processor = GitHubProcessor()
    combined_data = github_processor.combine_multiple_queries(queries, num_sources_per_query=5)
    combined_data.save_to_yaml("github_repositories.yaml")
    print(combined_data.to_dict())
