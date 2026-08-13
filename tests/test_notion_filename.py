from career_os.notion import NotionReviewQueue


def test_notion_file_name_preserves_extension_and_limits_display_name():
    filename = "Subrat_Rout_AT-T_Sr-Specialist-Tier-2-Application-Support-Engineer-Confluent-Kafka-Azure-Event-Hub-Azure-Ku_Resume.pdf"

    result = NotionReviewQueue._notion_file_name(filename)

    assert len(result) <= 100
    assert result.endswith(".pdf")
    assert result == filename[: 100 - len(".pdf")] + ".pdf"


def test_notion_file_name_keeps_short_names_unchanged():
    filename = "resume.docx"

    assert NotionReviewQueue._notion_file_name(filename) == filename
