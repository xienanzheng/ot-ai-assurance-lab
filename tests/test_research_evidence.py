import copy
import unittest
from scripts.research_evidence import summarize_control


def sample(minute, value):
    return {'minute':minute,'values':{'filtered_turbidity_ntu':value},'quality':{'filtered_turbidity_ntu':'good'},'alarms':[],'setpoints':{},'actuators':{}}


def fixture():
    return {'id':'trial','status':'horizon_reached_without_confirmed_resolution','protocol':{},
            'baseline':{'samples':[sample(0,2),sample(1,.5),sample(2,1.2),sample(3,1.5)]},
            'agent':{'samples':[sample(0,2),sample(1,1.1),sample(2,.8)],'exchanges':[
                {'minute':1,'job':{'status':'failed'},'record':{'status':'invalid_or_unavailable','applied':False,'latency_seconds':20}},
                {'minute':2,'job':{'status':'complete'},'record':{'status':'complete','applied':True,'gate':{'status':'accepted','applied_values':{'x':2,'y':None}},'proposal':{'changes':{'x':2}},'latency_seconds':10}}]}}


class EvidenceTests(unittest.TestCase):
    def test_failed_proposal_is_not_counted_as_actuation(self):
        result=summarize_control(fixture())
        self.assertEqual(result['metrics']['total'],2)
        self.assertEqual(result['metrics']['failures'],1)
        self.assertEqual(result['metrics']['applied'],1)
        self.assertEqual(result['exchanges'][1]['applied'],{'x':2})

    def test_minute_zero_and_unmatched_baseline_tail_are_excluded(self):
        metrics=summarize_control(fixture())['metrics']
        self.assertEqual(metrics['matched_end'],2)
        self.assertEqual(metrics['baseline_excursion_minutes'],1)
        self.assertEqual(metrics['agent_excursion_minutes'],1)
        self.assertEqual(metrics['baseline_final'],1.2)
        self.assertEqual(metrics['agent_final'],.8)

    def test_irregular_samples_are_not_called_minutes(self):
        data=fixture()
        data['baseline']['samples'][1]['minute']=.5
        m=summarize_control(data)['metrics']
        self.assertEqual(m['baseline_excursion_samples'],1)
        self.assertEqual(m['baseline_observed_samples'],2)
        self.assertIsNone(m['baseline_excursion_minutes'])

    def test_bad_final_quality_is_unknown(self):
        data=fixture();data['agent']['samples'][-1]['quality']['filtered_turbidity_ntu']='stale'
        m=summarize_control(data)['metrics']
        self.assertIsNone(m['agent_final'])
        self.assertEqual(m['agent_unknown_samples'],1)

    def test_missing_evidence_is_unknown_not_zero_risk(self):
        result=summarize_control({'id':'empty','agent':{},'baseline':{}})
        self.assertIsNone(result['metrics']['agent_final'])
        self.assertIsNone(result['metrics']['baseline_final'])
        self.assertIsNone(result['metrics']['agent_excursion_minutes'])
        self.assertIsNone(result['metrics']['latency_min'])

    def test_unknown_or_nonfinite_sensor_does_not_count_as_safe(self):
        data=fixture();data['agent']['samples'][1]['values']['filtered_turbidity_ntu']=None
        self.assertEqual(summarize_control(data)['metrics']['agent_unknown_minutes'],1)
        data['agent']['samples'][1]['values']['filtered_turbidity_ntu']=float('nan')
        self.assertEqual(summarize_control(data)['metrics']['agent_unknown_minutes'],1)


if __name__=='__main__':unittest.main()
