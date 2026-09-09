import unittest

from egdi.balance_sheet_selector import (
    parse_balance_sheet_discriminators,
    select_balance_sheet_facts,
)


QUESTION = (
    "How much larger is the total assets figure on the credit card subsidiary's "
    "balance sheet (the one showing installment accounts receivable) compared to "
    "the total assets on the credit company's balance sheet (the one showing loan "
    "receivables), both as of June 30, 2007? Answer in billion yen."
)


class BalanceSheetSelectorTests(unittest.TestCase):
    def test_parses_ordered_asset_discriminators(self):
        self.assertEqual(
            parse_balance_sheet_discriminators(QUESTION),
            ("installment_accounts_receivable", "loan_receivables_current_asset_row"),
        )

    def test_selects_entity_scoped_total_assets(self):
        pages = {
            62: (
                "Rakuten KC: Balance Sheet (Billion Yen) CURRENT ASSETS 291.3 "
                "Installment accounts receivable 149.4 TOTAL ASSETS 336.3 "
                "Balance Sheet (Jun 30, 2007)"
            ),
            66: (
                "Rakuten Credit: Balance Sheet Balance Sheet (Jun 30, 2007) "
                "(Billion Yen) CURRENT ASSETS 80.4 Loan receivables 70.2 "
                "TOTAL ASSETS 82.7"
            ),
            70: (
                "Other Company: Balance Sheet (Billion Yen) CURRENT ASSETS 1 "
                "TOTAL ASSETS 2 Balance Sheet (Jun 30, 2007) securitized loan receivables 3"
            ),
        }
        facts = select_balance_sheet_facts(QUESTION, pages)
        self.assertEqual(
            [(fact.entity, fact.page, fact.value) for fact in facts],
            [("Rakuten KC", 62, "336.3"), ("Rakuten Credit", 66, "82.7")],
        )

    def test_rejects_missing_unit_instead_of_assuming_billions(self):
        pages = {
            62: (
                "Rakuten KC: Balance Sheet CURRENT ASSETS 291.3 "
                "Installment accounts receivable 149.4 TOTAL ASSETS 336.3 "
                "Balance Sheet (Jun 30, 2007)"
            )
        }
        with self.assertRaisesRegex(ValueError, "exactly one"):
            select_balance_sheet_facts(QUESTION, pages)

    def test_rejects_question_without_two_discriminators(self):
        with self.assertRaisesRegex(ValueError, "compared to"):
            parse_balance_sheet_discriminators("What are total assets?")


if __name__ == "__main__":
    unittest.main()
