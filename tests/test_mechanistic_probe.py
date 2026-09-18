import unittest
try:
    import torch
except ImportError:
    torch = None
if torch is not None:
    from scripts.run_mechanistic_probe import matched_prompts, patch_last_position


@unittest.skipIf(torch is None, "Optional interpretability runtime is not installed")
class ProbeTests(unittest.TestCase):
    def test_matched_pair_changes_only_effluent_value(self):
        safe,alarm=matched_prompts(.5,1.2,False)
        self.assertEqual(safe.replace('0.500','1.200'),alarm)
        self.assertIn('A = continue',safe)
        swapped,_=matched_prompts(.5,1.2,True)
        self.assertIn('B = continue',swapped)
        self.assertIn('A = request',swapped)

    def test_patch_changes_only_last_position_and_keeps_original(self):
        original=torch.arange(12,dtype=torch.float16).reshape(1,3,4)
        changed=patch_last_position(original,torch.tensor([[30.,31.,32.,33.]]))
        self.assertEqual(changed.dtype,torch.float16)
        self.assertTrue(torch.equal(changed[0,:2],torch.tensor([[0.,1.,2.,3.],[4.,5.,6.,7.]],dtype=torch.float16)))
        self.assertTrue(torch.equal(changed[0,-1],torch.tensor([30.,31.,32.,33.],dtype=torch.float16)))
        self.assertEqual(original[0,-1,0].item(),8)

    def test_patch_rejects_shape_mismatch(self):
        with self.assertRaises(ValueError):patch_last_position(torch.zeros(1,3,4),torch.zeros(1,5))


if __name__=='__main__':unittest.main()
