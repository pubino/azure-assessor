"""Entry point for azure-assessor."""

from azure_assessor.app import AzureAssessorApp


def main() -> None:
    app = AzureAssessorApp()
    app.run()


if __name__ == "__main__":
    main()
