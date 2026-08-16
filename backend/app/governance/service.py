"""Human decisions and grounded proposal explanations."""

from __future__ import annotations

from typing import Any

from ..repositories import SQLiteRepository
from ..repositories.sqlite import stable_id
from ..services.contracts import utc_now


class GovernanceError(ValueError):
    pass


class GovernanceService:
    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def decide(
        self,
        *,
        proposal_id: str,
        action: str,
        actor_type: str,
        actor_id: str,
        modification: dict[str, Any] | None,
        note: str | None,
    ) -> dict[str, Any]:
        proposal = self.repository.get_proposal(proposal_id)
        if proposal is None:
            raise GovernanceError(f"la propuesta {proposal_id} no existe")
        if action == "modify" and not modification:
            raise GovernanceError(
                "modificar una propuesta exige enviar la modificación estructurada"
            )
        resulting_status = {
            "accept": "accepted",
            "reject": "rejected",
            "modify": "modified_pending_technical_review",
            "refer": "referred_to_technician",
        }[action]
        if action == "accept" and (
            proposal["validation_status"] != "validated" or actor_type != "technician"
        ):
            resulting_status = "pending_technical_review"
        created_at = utc_now()
        decision = {
            "id": stable_id(
                "decision",
                f"{proposal_id}|{actor_type}|{actor_id}|{action}|{created_at}",
            ),
            "proposal_id": proposal_id,
            "action": action,
            "resulting_status": resulting_status,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "modification": modification,
            "note": note,
            "created_at": created_at,
            "applied": resulting_status == "accepted",
        }
        self.repository.save_decision(decision)
        return decision

    def explanation(self, proposal_id: str) -> dict[str, Any] | None:
        proposal = self.repository.get_proposal(proposal_id)
        return proposal.get("explanation") if proposal else None

    def history(self, identifier: str) -> dict[str, Any] | None:
        proposal_id = identifier
        if identifier.startswith("decision-"):
            decision = self.repository.get_decision(identifier)
            if decision is None:
                return None
            proposal_id = decision["proposal_id"]
        proposal = self.repository.get_proposal(proposal_id)
        if proposal is None:
            return None
        return {
            "proposal": proposal,
            "decisions": self.repository.list_decisions(proposal_id),
            "audit": self.repository.audit_history("proposal", proposal_id),
        }
