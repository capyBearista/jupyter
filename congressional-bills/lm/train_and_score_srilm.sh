#!/bin/bash

ORDER=3
TRAIN_PREFIX=bill_summaries
SCORE_PREFIX=$1

mkdir -p ${SCORE_PREFIX}

echo "Preprocessing Training Data"
TRAIN=${TRAIN_PREFIX}.lctok
#cat ${TRAIN_PREFIX}.txt | python preprocess.py True > ${TRAIN}

echo "Building LM"
LM=${TRAIN_PREFIX}.${ORDER}gm.arpa
/nlp/users/ellie/software/srilm/lm/bin/i686-m64/ngram-count -order ${ORDER} -text ${TRAIN} -write ${TRAIN_PREFIX}.vocab
/nlp/users/ellie/software/srilm/lm/bin/i686-m64/ngram-count -order ${ORDER} -read ${TRAIN_PREFIX}.vocab -lm ${LM}

echo "Preprocessing Test Data"
SCORE=${SCORE_PREFIX}\/${SCORE_PREFIX}.lctok
##cat ${SCORE_PREFIX}/${SCORE_PREFIX}.txt | python preprocess.py False > ${SCORE}

echo "Scoring ${SCORE}"
SCORE_OUTPUT=${SCORE_PREFIX}\/${SCORE_PREFIX}.query_output.${ORDER}gm
/nlp/users/ellie/software/srilm/lm/bin/i686-m64/ngram -lm ${LM} -ppl ${SCORE_OUTPUT}

#cat ${SCORE_OUTPUT} | python pull_out_logprob.py > ${SCORE_OUTPUT}.logprob
#paste ${SCORE_OUTPUT}.logprob ${SCORE} | python score_sents.py > ${SCORE_OUTPUT}.logprob.normed
#paste ids.txt ${SCORE_OUTPUT}.logprob > ${SCORE_OUTPUT}.logprob.ided
#paste ids.txt ${SCORE_OUTPUT}.logprob.normed > ${SCORE_OUTPUT}.logprob.normed.ided

