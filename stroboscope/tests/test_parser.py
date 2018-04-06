from stroboscope.requirements import PARSER_MODEL, Requirements

TXT = """
( name : adza_zadazd, weight:32
) MIRROR 1.2.3.0/24, 2001:6a8:308f::/96 ON [A B C D], [->X]
CONFINE 1.2.3.0/24 ON [-> D ]
USING 5Mbps"""


print PARSER_MODEL.parse(TXT)
print Requirements.from_text(TXT)
print PARSER_MODEL.parse(str(Requirements.from_text(TXT)))
print Requirements.from_text(Requirements.from_text(TXT))
