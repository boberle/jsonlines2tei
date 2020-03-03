"""Convert a jsonlines file to a set of TEI-URS files, that can be import
in softwares such as TXM.


TEI-URS, jsonlines and TXM
==========================

The **TEI-URS** format is a XML-compliant TEI format used to store
coreferential annotations.  It contains both the text and stand-off
annotations, which can be stored in a two separate files.
The format is precisely described in the following paper:

    Loïc Grobol, Frédéric Landragin, and Serge Heiden. 2017.
    Interoperableannotation of (co)references in the Democrat project.
    Thirteenth Joint ISO-ACLWorkshop on Interoperable
    Semantic Annotation.



TEI-URS files can be imported into **TXM**, a text analysis environment
and graphical client based on CQP and R.  An newly released extension, the URS
extension (for Unit, Relation, Schema) allows the user to annotate or modify
coreference information on any text.  TXM can be downloaded at:

    http://textometrie.ens-lyon.fr/

and is described in the following paper:

    Heiden, S. (2010b). The TXM Platform: Building Open-Source Textual Analysis
    Software Compatible with the TEI Encoding Scheme. PACLIC24, Sendai, Japan.



The **jsonlines format** stores data for several texts (a corpus).  Each line
is a valid json document, as follows:

    {
      "clusters": [],
      "doc_key": "nw:docname",
      "sentences": [["This", "is", "the", "first", "sentence", "."],
                    ["This", "is", "the", "second", "."]],
      "speakers":  [["spk1", "spk1", "spk1", "spk1", "spk1", "spk1"],
                    ["spk2", "spk2", "spk2", "spk2", "spk2"]]
      "pos":       [["DET", "V", "DET", "ADJ", "NOUN", "PUNCT"],
                    ["DET", "V", "DET", "ADJ", "PUNCT"]],
      ...
    }

It is used for some coreference resolution systems, such as:

- https://github.com/kentonl/e2e-coref (English)
- https://github.com/kkjawz/coref-ee (English)
- https://github.com/boberle/cofr (French)


Usage
=====

The jsonlines format can contain many documents: each document will be
converted into two files: one for the text, with a `.xml` suffix, and one for
the stand-off annotation, with a `-urs.xml` suffix.  Each type of files can be
stored in the same directory, or in two distinct directories.

The command:

    python3 jsonlines2tei.py \
        --longest
        --xml-dir xml
        --urs-dir urs
        INPUT_FILE

would store all the documents from `INPUT_FILE` into two directories: `xml` for
texts and `urs` for annotations.  Referent names would be chosen from the
longest mention text in each coreferential chain (without the `--longest`
option, it the text of the first mention would have been chosen).

The files are named according to the `doc_key` key defined in each document of
the jsonlines file.
"""

# (C) Bruno Oberle 2020 - Mozilla Public Licence 2.0




import json
import os
import re
import argparse
from xml.sax.saxutils import escape


def _get_refnames(doc, first=True):
    tokens = [tok for sent in doc['sentences'] for tok in sent]
    if first:
        clusters = {
            id(cluster): " ".join(tokens[cluster[0][0]:cluster[0][1]+1])
            for cluster in doc['clusters']
        }
    else:
        def get_longest(cluster):
            cluster = sorted(cluster, key=lambda x: len(x), reverse=True)
            return tokens[cluster[0][0]:cluster[0][1]+1]
        clusters = {
            id(cluster): " ".join(get_longest(cluster))
            for cluster in doc['clusters']
        }
    used = set()
    for cluster, name in clusters.items():
        if name in used:
            counter = 1
            while name not in used:
                name += str(counter)
                counter += 1
            clusters[cluster] = name
        used.add(name)
    return clusters


def _build_text(doc):

    pars = {p[1] for p in doc['paragraphs']} if 'paragraphs' in doc else None
    t = 0
    p = 0
    res = "<text>"
    res += "<p>"

    for s, sent in enumerate(doc['sentences']):
        res += f'<s n="{s}">'
        for t_local, token in enumerate(sent):
            res += f'<w id="w_export_{t}" n="{t}">'
            res += f'<txm:form>{escape(token)}</txm:form>'
            if "pos" in doc:
                res += (f'<txm:ana resp="#txm" type="#frpos">'
                    f'{escape(doc["pos"][s][t_local])}</txm:ana>')
            res += '</w>'
            t += 1
        res += '</s>'
        if pars is not None and t-1 in pars and p < len(pars)-1:
            res += "</p><p>"
            p += 1
    res += "</p>"
    res += "</text>"

    return res



def _build_urs(doc, first=True):

    names = _get_refnames(doc, first=first)

    div = '<div type="unit-fs">'
    res = '<annotationGrp type="Unit" subtype="MENTION">'
    m = 0
    for cluster in doc['clusters']:
        for start, end in cluster: 
            res += f'<span id="u-MENTION-{m}" from="text:w_export_{start}" ' \
                f'to="text:w_export_{end}" ana="#u-MENTION-{m}-fs"/>'
            div += f'<fs id="u-MENTION-{m}-fs">'
            div += f'<f name="REF"><string>' \
                '{escape(names[id(cluster)])}</string></f>'
            div += '</fs>'
            m += 1
    res += "</annotationGrp>"
    div += "</div>"

    div += '<div type="relation-fs"/>'
    res += '<annotationGrp type="Schema" subtype="CHAINE">'
    div += '<div type="schema-fs">'
    offset = 0
    for c, cluster in enumerate(doc['clusters']): 
        target = " ".join(f'#u-MENTION-{m+offset}' for m in range(len(cluster)))
        offset += len(cluster)
        res += f'<link id="s-CHAINE-{c}" target="{target}" ' \
            f'ana="#s-CHAINE-{c}-fs"/>'
        div += f'<fs id="s-CHAINE-{c}-fs">'
        div += f'<f name="REF"><string>' \
            '{escape(names[id(cluster)])}</string></f>'
        div += f'<f name="NB MAILLONS"><string>{len(cluster)}</string></f>'
        div += '</fs>'
    res += "</annotationGrp>"
    div += "</div>"

    res = f'<standOff><annotations type="coreference">{res}{div}' \
        '</annotations></standOff>'

    return res


def _get_teis(doc, xml_text, xml_urs):
    header = (f'<teiHeader><fileDesc><titleStmt><title>{doc["doc_key"]}'
        f'</title></titleStmt></fileDesc></teiHeader>')
    text = (f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:txm="http://textometrie.org/1.0">'
        f'{header}{xml_text}</TEI>')
    urs = (f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<tei:TEI xmlns:tei="http://www.tei-c.org/ns/1.0">'
        f'{header}<text></text>{xml_urs}</tei:TEI>')
    return text, urs


def jsonlines2tei(doc, xml_dir, urs_dir, first=True):
    xml_text, xml_urs = _get_teis(
        doc,
        _build_text(doc),
        _build_urs(doc, first))
    fn = doc['doc_key']
    fn = re.sub(r'[^-a-zA-Z0-9_]', '_', fn)
    fn = re.sub(r'_+', '_', fn)
    open(os.path.join(xml_dir, f"{fn}.xml"), 'w').write(xml_text)
    open(os.path.join(urs_dir, f"{fn}-urs.xml"), 'w').write(xml_urs)



def parse_args():
    # definition
    parser = argparse.ArgumentParser(prog="jsonlines2tei",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # arguments (not options)
    #parser.add_argument("infpaths", nargs="+", help="input files")
    parser.add_argument("infpath", default="", help="input file")
    #parser.add_argument("outfpath", default="", help="output file")
    # options
    parser.add_argument("--longest", dest="longest", default=False,
       action="store_true",
       help="used the longest mention for the referent name")
    parser.add_argument("--xml-dir", dest="xml_dir", required=True,
        help="xml directory")
    parser.add_argument("--urs-dir", dest="urs_dir", required=True,
        help="urs directory")
    # reading
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    for line in open(args.infpath):
        doc = json.loads(line)
        jsonlines2tei(doc, xml_dir=args.xml_dir, urs_dir=args.urs_dir,
            first=not args.longest)


if __name__ == '__main__':
    main()

