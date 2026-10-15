# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Durable Docker mutation fences, using the sequencer's existing SQLite DB.

INFLIGHT is deliberately never expired or replayed. Only a durably observed
response may enter the signing outbox; immutable-log confirmation releases it.
"""
from typing import Any, Dict, Literal, Optional
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import database as db

router = APIRouter()
# app.py replaces this with the commit/query sequencer lock before serving.
sequencer_lock = threading.Lock()


class MutationReserveRequest(BaseModel):
    mutation_id: str = Field(pattern=r'^mutation-[0-9a-f]{32}$')
    chain_id: Literal['default'] = 'default'
    operation_type: Literal['create', 'start', 'stop', 'rm']
    op_record: Dict[str, Any]
    workload_id: Optional[str] = None
    launch_id: Optional[str] = None


class MutationResultRequest(BaseModel):
    op_record: Dict[str, Any]


class MutationSubmissionRequest(BaseModel):
    submission: Dict[str, Any]


def _change(action, *args):
    # Serialize durable fence changes with collection snapshots and commits.
    # Database transactions provide persistence; this lock orders service actions.
    try:
        with sequencer_lock:
            return action(*args)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/mutations/reserve')
def reserve_mutation(req: MutationReserveRequest):
    if req.op_record.get('operation', {}).get('type') != req.operation_type:
        raise HTTPException(status_code=400, detail='Mutation operation type mismatch')
    return _change(db.reserve_docktap_mutation, req.mutation_id, req.chain_id, req.operation_type,
                   {'op_record': req.op_record, 'workload_id': req.workload_id, 'launch_id': req.launch_id})


@router.post('/mutations/{mutation_id}/result')
def mutation_result(mutation_id: str, req: MutationResultRequest):
    return _change(db.complete_docktap_mutation, mutation_id, req.model_dump())


@router.post('/mutations/{mutation_id}/submission')
def mutation_submission(mutation_id: str, req: MutationSubmissionRequest):
    return _change(db.save_docktap_submission, mutation_id, req.submission)


@router.get('/mutations')
def recover_mutations():
    return {'mutations': db.get_docktap_mutations()}
