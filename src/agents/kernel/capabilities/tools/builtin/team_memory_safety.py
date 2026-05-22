from __future__ import annotations

import re
from dataclasses import dataclass

from agents.kernel.memory_paths import is_team_memory_path


@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class SecretMatch:
    rule_id: str
    label: str


_ANTHROPIC_KEY_PREFIX = "-".join(("sk", "ant", "api"))


def _rule(rule_id: str, source: str, flags: int = 0) -> SecretRule:
    return SecretRule(rule_id, re.compile(source, flags))


_SECRET_RULES = (
    _rule("aws-access-token", r"\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b"),
    _rule("gcp-api-key", r"\b(AIza[\w-]{35})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule(
        "azure-ad-client-secret",
        r"(?:^|[\\'\"`\s>=:(,)])"
        r"([a-zA-Z0-9_~.]{3}\dQ~[a-zA-Z0-9_~.-]{31,34})"
        r"(?:$|[\\'\"`\s<),])",
    ),
    _rule("digitalocean-pat", r"\b(dop_v1_[a-f0-9]{64})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("digitalocean-access-token", r"\b(doo_v1_[a-f0-9]{64})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule(
        "anthropic-api-key",
        rf"\b({_ANTHROPIC_KEY_PREFIX}03-[a-zA-Z0-9_\-]{{93}}AA)(?:[`'\"\s;]|\\[nr]|$)",
    ),
    _rule("anthropic-admin-api-key", r"\b(sk-ant-admin01-[a-zA-Z0-9_\-]{93}AA)(?:[`'\"\s;]|\\[nr]|$)"),
    _rule(
        "openai-api-key",
        r"\b("
        r"sk-(?:proj|svcacct|admin)-"
        r"(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})"
        r"T3BlbkFJ"
        r"(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})\b"
        r"|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}"
        r")(?:[`'\"\s;]|\\[nr]|$)",
    ),
    _rule("huggingface-access-token", r"\b(hf_[a-zA-Z]{34})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("github-pat", r"ghp_[0-9a-zA-Z]{36}"),
    _rule("github-fine-grained-pat", r"github_pat_\w{82}"),
    _rule("github-app-token", r"(?:ghu|ghs)_[0-9a-zA-Z]{36}"),
    _rule("github-oauth", r"gho_[0-9a-zA-Z]{36}"),
    _rule("github-refresh-token", r"ghr_[0-9a-zA-Z]{36}"),
    _rule("gitlab-pat", r"glpat-[\w-]{20}"),
    _rule("gitlab-deploy-token", r"gldt-[0-9a-zA-Z_\-]{20}"),
    _rule("slack-bot-token", r"xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*"),
    _rule("slack-user-token", r"xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}"),
    _rule("slack-app-token", r"xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]+", re.IGNORECASE),
    _rule("twilio-api-key", r"SK[0-9a-fA-F]{32}"),
    _rule("sendgrid-api-token", r"\b(SG\.[a-zA-Z0-9=_\-.]{66})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("npm-access-token", r"\b(npm_[a-zA-Z0-9]{36})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("pypi-upload-token", r"pypi-AgEIcHlwaS5vcmc[\w-]{50,1000}"),
    _rule("databricks-api-token", r"\b(dapi[a-f0-9]{32}(?:-\d)?)(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("hashicorp-tf-api-token", r"[a-zA-Z0-9]{14}\.atlasv1\.[a-zA-Z0-9\-_=]{60,70}"),
    _rule("pulumi-api-token", r"\b(pul-[a-f0-9]{40})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("postman-api-token", r"\b(PMAK-[a-fA-F0-9]{24}-[a-fA-F0-9]{34})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("grafana-api-key", r"\b(eyJrIjoi[A-Za-z0-9+/]{70,400}={0,3})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule("grafana-cloud-api-token", r"\b(glc_[A-Za-z0-9+/]{32,400}={0,3})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule(
        "grafana-service-account-token",
        r"\b(glsa_[A-Za-z0-9]{32}_[A-Fa-f0-9]{8})(?:[`'\"\s;]|\\[nr]|$)",
    ),
    _rule("sentry-user-token", r"\b(sntryu_[a-f0-9]{64})(?:[`'\"\s;]|\\[nr]|$)"),
    _rule(
        "sentry-org-token",
        r"\bsntrys_eyJpYXQiO[a-zA-Z0-9+/]{10,200}"
        r"(?:LCJyZWdpb25fdXJs|InJlZ2lvbl91cmwi|cmVnaW9uX3VybCI6)"
        r"[a-zA-Z0-9+/]{10,200}={0,2}_[a-zA-Z0-9+/]{43}",
    ),
    _rule(
        "stripe-access-token",
        r"\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})(?:[`'\"\s;]|\\[nr]|$)",
    ),
    _rule("shopify-access-token", r"shpat_[a-fA-F0-9]{32}"),
    _rule("shopify-shared-secret", r"shpss_[a-fA-F0-9]{32}"),
    _rule(
        "private-key",
        r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----"
        r"[\s\S-]{64,}?"
        r"-----END[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----",
        re.IGNORECASE,
    ),
)
_SPECIAL_LABELS = {
    "ad": "AD",
    "api": "API",
    "aws": "AWS",
    "digitalocean": "DigitalOcean",
    "gcp": "GCP",
    "github": "GitHub",
    "gitlab": "GitLab",
    "hashicorp": "HashiCorp",
    "huggingface": "HuggingFace",
    "npm": "NPM",
    "oauth": "OAuth",
    "openai": "OpenAI",
    "pat": "PAT",
    "pypi": "PyPI",
    "sendgrid": "SendGrid",
    "tf": "TF",
}


def check_team_memory_secrets(path: str, content: str) -> str | None:
    if not is_team_memory_path(path):
        return None
    matches = scan_for_secrets(content)
    if not matches:
        return None
    labels = ", ".join(match.label for match in matches)
    return (
        "Content contains potential secrets (%s) and cannot be written to team memory. "
        "Team memory is shared with all repository collaborators. "
        "Remove the sensitive content and try again."
    ) % labels


def scan_for_secrets(content: str) -> list[SecretMatch]:
    text = str(content or "")
    matches: list[SecretMatch] = []
    seen: set[str] = set()
    for rule in _SECRET_RULES:
        if rule.rule_id in seen:
            continue
        if rule.pattern.search(text):
            seen.add(rule.rule_id)
            matches.append(SecretMatch(rule.rule_id, _secret_label(rule.rule_id)))
    return matches


def _secret_label(rule_id: str) -> str:
    return " ".join(_SPECIAL_LABELS.get(part, part.capitalize()) for part in rule_id.split("-"))
