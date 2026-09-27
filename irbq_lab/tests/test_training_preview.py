"""Throttled, detached training snapshots do not change fitted coefficients."""
import unittest
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model,Biquad
from irbq.trainer import train,TrainConfig


class TestTrainingPreview(unittest.TestCase):
    def test_throttle_isolation_and_numerical_equivalence(self):
        model=Model(44100,np.array([1.,0.,0.,0.]),[Biquad('Peak',f=800,q=1,gain=0)])
        target=Model(44100,np.array([1.]),[Biquad('Peak',f=1100,q=1,gain=5)]).render(length=512)
        cfg=TrainConfig(mode='bq',iterations=20,restarts=1)
        reference=train(target,model,cfg)
        previews=[];clock=[0.]
        def tick():
            clock[0]+=.05
            return clock[0]
        def capture(candidate):
            previews.append((clock[0],candidate))
        with patch('irbq.trainer.time.perf_counter',side_effect=tick):
            result=train(target,model,cfg,preview=capture,preview_interval=.5)
        self.assertGreater(len(previews),1)
        for previous,current in zip(previews,previews[1:]):
            self.assertGreaterEqual(current[0]-previous[0],.5)
        np.testing.assert_allclose(result.response(np.geomspace(80,8000,100)),
                                   reference.response(np.geomspace(80,8000,100)),rtol=1e-12,atol=1e-12)
        previews[0][1].fir[0]=99
        previews[0][1].sections[0].gain=99
        self.assertEqual(model.fir[0],1);self.assertEqual(model.sections[0].gain,0)
        self.assertNotEqual(result.sections[0].gain,99)

    def test_invalid_interval(self):
        model=Model(44100,np.array([1.]),[])
        for interval in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                train(np.array([1.]),model,TrainConfig(),preview=lambda m:None,preview_interval=interval)

    def test_joint_preview_keeps_conditional_fir_result(self):
        model=Model(44100,np.r_[1.,np.zeros(7)],[Biquad('Peak',f=800,q=1,gain=1)])
        target=Model(44100,np.array([1.,.2,-.1,0.]),[Biquad('Peak',f=1000,q=.8,gain=4)]).render(length=256)
        cfg=TrainConfig(mode='joint',iterations=5,restarts=1,initialize=False)
        reference=train(target,model,cfg)
        frames=[]
        with patch('irbq.trainer.time.perf_counter',side_effect=iter(np.arange(0,1000,.6))):
            result=train(target,model,cfg,preview=frames.append)
        self.assertGreater(len(frames),1)
        np.testing.assert_allclose(result.fir,reference.fir,rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(result.response(np.geomspace(80,8000,100)),
                                   reference.response(np.geomspace(80,8000,100)),rtol=1e-12,atol=1e-12)
